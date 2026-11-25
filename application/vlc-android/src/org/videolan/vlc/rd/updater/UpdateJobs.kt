/* SPDX-License-Identifier: GPL-2.0-or-later */
package org.videolan.vlc.rd.updater

import org.videolan.vlc.util.RdUpdateCheck

import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import android.content.SharedPreferences
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Network
import android.net.NetworkRequest
import android.os.Build
import org.videolan.tools.Settings
import kotlinx.coroutines.runBlocking
import java.io.IOException
import java.io.RandomAccessFile
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.ReentrantLock

object UpdateJobs {
    const val CHECK_JOB=0x52445501
    const val DOWNLOAD_JOB=0x52445502
    private var listener:SharedPreferences.OnSharedPreferenceChangeListener?=null
    private fun scheduler(c:Context)=c.getSystemService(Context.JOB_SCHEDULER_SERVICE) as JobScheduler
    private fun info(c:Context,id:Int)=JobInfo.Builder(id,ComponentName(c,UpdateJobService::class.java))
    @Synchronized
    fun initialize(c:Context){
        val app=c.applicationContext
        if(UpdateTrust.edition(app.packageName)==null || listener!=null)return
        Executors.newSingleThreadExecutor().apply { execute { runCatching { UpdateState.reconcile(app) } }; shutdown() };scheduleCheck(app)
        if(listener==null){listener=SharedPreferences.OnSharedPreferenceChangeListener { _,key->
            if(key==RdUpdateCheck.KEY_CHECK || key==RdUpdateCheck.KEY_CHANNEL)scheduleCheck(app)
            if(key==RdUpdateCheck.KEY_WIFI){val s=UpdateState.snapshot(app);if(s.phase in setOf(Phase.QUEUED,Phase.DOWNLOADING)&&s.id!=null){pause(app,s.id);resume(app,s.id)}}
        };Settings.getInstance(app).registerOnSharedPreferenceChangeListener(listener!!)}
        val s=UpdateState.snapshot(app)
        if(s.phase in setOf(Phase.QUEUED,Phase.DOWNLOADING)&&s.id!=null&&scheduler(app).allPendingJobs.none{it.id==DOWNLOAD_JOB}){
            UpdateState.transition(app,s.id,setOf(Phase.DOWNLOADING),Phase.QUEUED);scheduleDownload(app,s.id)
        }
    }
    fun scheduleCheck(c:Context){val j=scheduler(c);if(!RdUpdateCheck.enabled(c)){j.cancel(CHECK_JOB);return};if(j.allPendingJobs.any{it.id==CHECK_JOB})return
        j.schedule(info(c,CHECK_JOB).setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPeriodic(TimeUnit.DAYS.toMillis(1)).setPersisted(true).build())}
    private fun scheduleDownload(c:Context,id:String){
        val network=if(RdUpdateCheck.wifiOnly(c))JobInfo.NETWORK_TYPE_UNMETERED else JobInfo.NETWORK_TYPE_ANY
        val builder=info(c,DOWNLOAD_JOB).setPersisted(true).setBackoffCriteria(30000,JobInfo.BACKOFF_POLICY_EXPONENTIAL)
        if (RdUpdateCheck.wifiOnly(c) && Build.VERSION.SDK_INT>=28) builder.setRequiredNetwork(
            NetworkRequest.Builder().addTransportType(NetworkCapabilities.TRANSPORT_WIFI).addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET).build())
        else builder.setRequiredNetworkType(network)
        val result=runCatching{scheduler(c).schedule(builder.build())}.getOrDefault(JobScheduler.RESULT_FAILURE)
        if(result!=JobScheduler.RESULT_SUCCESS)UpdateState.transition(c,id,setOf(Phase.QUEUED),Phase.FAILED,"schedule_failed")
    }
    fun resume(c:Context,id:String){if(UpdateState.transition(c,id,setOf(Phase.PAUSED,Phase.FAILED),Phase.QUEUED)){UpdateState.resetRetries(c,id);scheduleDownload(c,id)}}
    fun pause(c:Context,id:String){if(UpdateState.transition(c,id,setOf(Phase.QUEUED,Phase.DOWNLOADING),Phase.PAUSED))scheduler(c).cancel(DOWNLOAD_JOB)}
    fun discard(c:Context,id:String){pause(c,id);UpdateState.discard(c,id)}
    /** Bind APK transfers to a concrete Wi-Fi network, not merely a preflight network check. */
    @Suppress("DEPRECATION")
    fun wifiNetwork(c:Context): Network? {
        val cm=c.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        return cm.allNetworks.firstOrNull { network ->
            val caps=cm.getNetworkCapabilities(network)
            caps?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)==true && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        }
    }

}

class UpdateJobService:JobService(){
    private val pool=Executors.newFixedThreadPool(2)
    private val active=ConcurrentHashMap<Int,Future<*>>()
    override fun onStartJob(params:JobParameters):Boolean{
        val id=params.jobId
        lateinit var future:java.util.concurrent.FutureTask<Unit>
        future=java.util.concurrent.FutureTask<Unit>{
            var retry=false
            try{when(id){
                UpdateJobs.CHECK_JOB->{val m=runBlocking{RdUpdateCheck.check(applicationContext,true)};if(m!=null&&!RdUpdateCheck.alreadyNotified(applicationContext,m)){if(UpdateNotifications.available(applicationContext,m))RdUpdateCheck.setNotified(applicationContext,m)}}
                UpdateJobs.DOWNLOAD_JOB->retry=UpdateDownload.run(applicationContext)
            }}catch(e:InterruptedException){Thread.currentThread().interrupt();retry=id==UpdateJobs.DOWNLOAD_JOB}
            catch(e:Exception){if(id==UpdateJobs.DOWNLOAD_JOB)retry=true;android.util.Log.w("VLC/RdUpdater","Update job did not finish: ${e.javaClass.simpleName}")}
            finally{if(active.remove(id,future)&&!Thread.currentThread().isInterrupted)jobFinished(params,retry)}
        }
        active.put(id,future)?.cancel(true);pool.execute(future);return true
    }
    override fun onStopJob(params:JobParameters):Boolean{active.remove(params.jobId)?.cancel(true);return params.jobId==UpdateJobs.DOWNLOAD_JOB&&UpdateState.snapshot(this).phase in setOf(Phase.QUEUED,Phase.DOWNLOADING)}
    override fun onDestroy(){active.values.forEach{it.cancel(true)};active.clear();pool.shutdownNow();super.onDestroy()}
}

internal object UpdateDownload {
    private val lock=ReentrantLock()
    private fun retry(c:Context,id:String,reason:String,count:Boolean=true):Boolean {
        if(!UpdateState.snapshot(c).let{it.id==id&&it.phase==Phase.DOWNLOADING})return false
        val attempts=if(count)UpdateState.recordRetry(c,id) else 0
        val retry=attempts<UpdateTrust.MAX_RETRIES
        UpdateState.transition(c,id,setOf(Phase.DOWNLOADING),if(retry)Phase.QUEUED else Phase.FAILED,reason)
        return retry
    }
    fun run(c:Context):Boolean{
        if(!lock.tryLock())return true
        try{
            val s=UpdateState.snapshot(c);val id=s.id?:return false
            if(!UpdateState.transition(c,id,setOf(Phase.QUEUED,Phase.DOWNLOADING),Phase.DOWNLOADING))return false
            val network = if(RdUpdateCheck.wifiOnly(c)) UpdateJobs.wifiNetwork(c) ?: return retry(c,id,"wifi_unavailable",count=false) else null
            val manifest=try{UpdateState.load(c,id)}catch(e:Exception){UpdateState.transition(c,id,setOf(Phase.DOWNLOADING),Phase.FAILED,"metadata_invalid");return false}
            val partial=UpdateState.partial(c,id);val apk=UpdateState.apk(c,id)
            try{
                if(partial.length()>manifest.asset.size)partial.delete()
                if(apk.exists()){InstalledIdentity.verifyApk(c,apk,manifest);UpdateState.transition(c,id,setOf(Phase.DOWNLOADING),Phase.READY);return false}
                var offset=partial.length()
                if(offset<manifest.asset.size){
                    val conn=UpdateHttp.open(manifest.url,offset,network)
                    try{
                        if(conn.responseCode==200)offset=0
                        else {require(offset>0);require(conn.getHeaderField("Content-Range")=="bytes $offset-${manifest.asset.size-1}/${manifest.asset.size}"){"Invalid resume range"}}
                        RandomAccessFile(partial,"rw").use{out->out.setLength(offset);out.seek(offset);conn.inputStream.use{input->val buf=ByteArray(65536);var received=offset
                            while(true){if(Thread.currentThread().isInterrupted||UpdateState.snapshot(c).let{it.id!=id||it.phase!=Phase.DOWNLOADING})return false
                                if(RdUpdateCheck.wifiOnly(c)&&network==null)return retry(c,id,"wifi_unavailable",count=false)
                                val n=input.read(buf);if(n<0)break;require(received+n<=manifest.asset.size){"Unexpected APK size"};out.write(buf,0,n);received+=n}
                            if(received!=manifest.asset.size)throw IOException("Incomplete download");out.fd.sync()
                        }}
                    }finally{conn.disconnect()}
                }
                if(UpdateState.snapshot(c).let{it.id!=id||it.phase!=Phase.DOWNLOADING})return false
                InstalledIdentity.verifyApk(c,partial,manifest)
                check(partial.renameTo(apk))
                if(UpdateState.transition(c,id,setOf(Phase.DOWNLOADING),Phase.READY))UpdateNotifications.ready(c)
                return false
            }catch(e:HttpFailure){
                return if(UpdateTrust.retryableHttp(e.status)) retry(c,id,"http_${e.status}") else {
                    UpdateState.transition(c,id,setOf(Phase.DOWNLOADING),Phase.FAILED,"http_${e.status}");false
                }
            }catch(e:IOException){return retry(c,id,"download_interrupted")}
            catch(e:Exception){partial.delete();apk.delete();UpdateState.transition(c,id,setOf(Phase.DOWNLOADING),Phase.FAILED,"apk_invalid");return false}
        }finally{lock.unlock()}
    }
}
