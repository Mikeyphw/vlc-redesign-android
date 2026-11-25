/* SPDX-License-Identifier: GPL-2.0-or-later */
package org.videolan.vlc.rd.updater

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import org.videolan.vlc.R
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

internal object UpdateNotifications {
    private const val CHANNEL="rd_fork_updates"
    private const val ID=0x524455
    private fun send(c:Context,title:String,text:String,intent:Intent,token:PendingIntent?=null):Boolean {
        if(Build.VERSION.SDK_INT>=33&&c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)return false
        val manager=c.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if(Build.VERSION.SDK_INT>=26){if(!manager.areNotificationsEnabled())return false;manager.createNotificationChannel(NotificationChannel(CHANNEL,c.getString(R.string.rd_m10_title),NotificationManager.IMPORTANCE_DEFAULT))}
        val pending=token ?: PendingIntent.getActivity(c,ID,intent,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val n=NotificationCompat.Builder(c,CHANNEL).setSmallIcon(android.R.drawable.stat_sys_download_done).setContentTitle(title).setContentText(text).setAutoCancel(true).setContentIntent(pending).build()
        return runCatching{manager.notify(ID,n);true}.getOrDefault(false)
    }
    fun available(c:Context,m:UpdateManifest)=send(c,c.getString(R.string.rd_m10_title),c.getString(R.string.rd_update_available,m.version),UpdateActivity.intent(c))
    fun ready(c:Context)=send(c,c.getString(R.string.rd_m10_title),c.getString(R.string.rd_m10_ready),UpdateActivity.intent(c))
    fun confirmation(c:Context,token:PendingIntent)=send(c,c.getString(R.string.rd_m10_title),c.getString(R.string.rd_m10_confirm),UpdateActivity.intent(c),token)
}

internal object UpdateInstaller {
    private val installLock = ReentrantLock()
    fun <T> withInstallLock(block: () -> T): T = installLock.withLock(block)
    private fun confirmationIntent(c: Context, session: Int) =
        Intent(c, UpdateConfirmationActivity::class.java).setAction(c.packageName + ".RD_CONFIRM.$session")
            .putExtra("rd_session", session).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    fun confirmation(c: Context, session: Int): PendingIntent? =
        PendingIntent.getActivity(c, session, confirmationIntent(c, session), PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE)
    fun setConfirmation(c: Context, session: Int, intent: Intent): PendingIntent =
        requireNotNull(PendingIntent.getActivity(c, session, confirmationIntent(c, session).putExtra("rd_confirmation", intent),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
    fun clearConfirmation(c: Context, session: Int) { confirmation(c, session)?.cancel() }
    fun canInstall(c:Context)=Build.VERSION.SDK_INT<26||c.packageManager.canRequestPackageInstalls()
    fun install(c:Context,id:String) = withInstallLock { installLocked(c,id) }
    private fun installLocked(c:Context,id:String){
        require(canInstall(c)){"Installation permission denied"}
        if(!UpdateState.transition(c,id,setOf(Phase.READY),Phase.INSTALLING,session=-1))return
        val installer=c.packageManager.packageInstaller;var sessionId=-1;var commitAttempted=false
        try{
            val m=UpdateState.load(c,id);val apk=UpdateState.apk(c,id);InstalledIdentity.verifyApk(c,apk,m)
            val params=PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply{
                setAppPackageName(c.packageName);setSize(m.asset.size)
                if(Build.VERSION.SDK_INT>=31)setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED)
            }
            sessionId=installer.createSession(params)
            require(UpdateState.transition(c,id,setOf(Phase.INSTALLING),Phase.INSTALLING,session=sessionId))
            installer.openSession(sessionId).use{session->
                session.openWrite("base.apk",0,m.asset.size).use{out->apk.inputStream().use{it.copyTo(out)};session.fsync(out)}
                val callback=Intent(c,UpdateInstallReceiver::class.java).setAction(c.packageName+".RD_UPDATE_RESULT").putExtra("rd_update_id",id).putExtra("rd_session",sessionId)
                val flags=PendingIntent.FLAG_UPDATE_CURRENT or if(Build.VERSION.SDK_INT>=31)PendingIntent.FLAG_MUTABLE else 0
                val pending=requireNotNull(PendingIntent.getBroadcast(c,sessionId,callback,flags))
                commitAttempted=true;session.commit(pending.intentSender)
            }
        }catch(e:Exception){
            // If commit was attempted, do not replay or abandon an uncertain installation outcome.
            if(!commitAttempted){if(sessionId>=0)runCatching{installer.abandonSession(sessionId)};UpdateState.transition(c,id,setOf(Phase.INSTALLING),Phase.READY,"install_failed",-1)}
        }
    }
    fun abandon(c:Context,id:String) = withInstallLock { abandonLocked(c,id) }
    private fun abandonLocked(c:Context,id:String){
        val s=UpdateState.snapshot(c);if(s.id!=id||s.phase !in setOf(Phase.CONFIRM,Phase.INSTALLING))return
        UpdateState.reconcile(c);val now=UpdateState.snapshot(c);if(now.phase==Phase.INSTALLED)return
        val installer=c.packageManager.packageInstaller
        if(s.session>=0){try{installer.abandonSession(s.session)}catch(e:Exception){UpdateState.reconcile(c);return};clearConfirmation(c,s.session)}
        UpdateState.transition(c,id,setOf(Phase.CONFIRM,Phase.INSTALLING),Phase.READY,"install_cancelled",-1)
    }
}

class UpdateInstallReceiver:BroadcastReceiver(){
    @Suppress("DEPRECATION")
    override fun onReceive(context:Context,intent:Intent){
        if(intent.action!=context.packageName+".RD_UPDATE_RESULT")return
        val id=intent.getStringExtra("rd_update_id")?:return;val session=intent.getIntExtra("rd_session",-1)
        val state=UpdateState.snapshot(context)
        if(state.id!=id||state.session!=session||session<0||state.phase !in setOf(Phase.INSTALLING,Phase.CONFIRM))return
        if(intent.hasExtra(PackageInstaller.EXTRA_SESSION_ID)&&intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID,-1)!=session)return
        when(intent.getIntExtra(PackageInstaller.EXTRA_STATUS,Int.MIN_VALUE)){
            PackageInstaller.STATUS_PENDING_USER_ACTION->{
                val confirm=if(Build.VERSION.SDK_INT>=33)intent.getParcelableExtra(Intent.EXTRA_INTENT,Intent::class.java) else intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                if(confirm==null){UpdateInstaller.abandon(context,id);return}
                confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                if(UpdateState.transition(context,id,setOf(Phase.INSTALLING,Phase.CONFIRM),Phase.CONFIRM)){
                    val token=UpdateInstaller.setConfirmation(context,session,confirm)
                    UpdateNotifications.confirmation(context,token)
                }
            }
            PackageInstaller.STATUS_SUCCESS->{
                UpdateInstaller.clearConfirmation(context,session)
                // APK hash verification can be slow: use an asynchronous broadcast completion.
                val pending=goAsync();val app=context.applicationContext
                Thread { try { UpdateState.reconcile(app) } finally { pending.finish() } }.start()
            }
            Int.MIN_VALUE->return
            else->{UpdateInstaller.clearConfirmation(context,session);UpdateState.transition(context,id,setOf(Phase.INSTALLING,Phase.CONFIRM),Phase.READY,"install_failed",-1)}
        }
    }
}

/** Private relay: Android owns the confirmation Intent; the system PendingIntent retains it across process death. */
class UpdateConfirmationActivity : android.app.Activity() {
    @Suppress("DEPRECATION")
    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        super.onCreate(savedInstanceState)
        val session = intent.getIntExtra("rd_session", -1)
        val snapshot = UpdateState.snapshot(this)
        if (snapshot.phase == Phase.CONFIRM && session >= 0 && snapshot.session == session &&
            intent.action == packageName + ".RD_CONFIRM.$session") {
            val confirmation = if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra("rd_confirmation", Intent::class.java)
                else intent.getParcelableExtra<Intent>("rd_confirmation")
            if (confirmation != null) try { startActivity(confirmation) } catch (e: Exception) {
                android.widget.Toast.makeText(this,R.string.rd_m10_confirmation_lost,android.widget.Toast.LENGTH_LONG).show()
            }
        }
        finish()
    }
}
