/* SPDX-License-Identifier: GPL-2.0-or-later */
package org.videolan.vlc.rd.updater

import org.videolan.vlc.util.RdUpdateCheck

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.videolan.tools.Settings
import org.videolan.vlc.R

/** One canonical phone/tablet/TV update screen; all installation begins with an explicit action. */
class UpdateActivity:AppCompatActivity(){
    companion object{
        fun intent(c:Context)=Intent(c,UpdateActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        fun open(c:Context){c.startActivity(intent(c))}
    }
    private lateinit var titleView:TextView;private lateinit var info:TextView;private lateinit var notes:TextView
    private lateinit var progress:ProgressBar;private lateinit var check:Button;private lateinit var primary:Button;private lateinit var secondary:Button
    private var found:UpdateManifest?=null;private var checking=false;private var installing=false
    private var checkError:String?=null;private var checked=false
    private var installed:InstalledRelease?=null; private var installedVersion=""
    private var selectedNotes=""
    private lateinit var channelButtons:RadioGroup
    private var loadingIdentity=true
    private val handler=Handler(Looper.getMainLooper())
    private val ticker=object:Runnable{override fun run(){render();handler.postDelayed(this,500)}}
    override fun onCreate(savedInstanceState:Bundle?){super.onCreate(savedInstanceState);title=getString(R.string.rd_m10_title)
        val layout=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;val p=dp(20);setPadding(p,p,p,p)}
        fun text(size:Float)=TextView(this).apply{textSize=size;layout.addView(this,LinearLayout.LayoutParams(-1,-2))}
        fun button(label:Int,action:()->Unit)=Button(this).apply{setText(label);minHeight=dp(48);isFocusable=true;setOnClickListener{action()};layout.addView(this,LinearLayout.LayoutParams(-1,-2))}
        titleView=text(22f);titleView.text=getString(R.string.rd_m10_title)
        info=text(16f).apply{setPadding(0,dp(12),0,dp(12));accessibilityLiveRegion=View.ACCESSIBILITY_LIVE_REGION_POLITE}
        progress=ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal).apply{max=1000;contentDescription=getString(R.string.rd_m10_progress);layout.addView(this,LinearLayout.LayoutParams(-1,dp(12)))}
        notes=text(14f).apply{setPadding(0,dp(12),0,dp(12))}
        check=button(R.string.rd_m10_check){checkNow()}
        primary=button(R.string.download){primaryAction()}
        secondary=button(android.R.string.cancel){secondaryAction()}
        val prefs=Settings.getInstance(this)
        Switch(this).apply{setText(R.string.rd_check_updates);isChecked=prefs.getBoolean(RdUpdateCheck.KEY_CHECK,true);minHeight=dp(48);layout.addView(this);setOnCheckedChangeListener{_,v->prefs.edit().putBoolean(RdUpdateCheck.KEY_CHECK,v).apply();UpdateJobs.scheduleCheck(this@UpdateActivity)}}
        Switch(this).apply{setText(R.string.rd_m10_wifi);isChecked=RdUpdateCheck.wifiOnly(this@UpdateActivity);minHeight=dp(48);layout.addView(this);setOnCheckedChangeListener{_,v->prefs.edit().putBoolean(RdUpdateCheck.KEY_WIFI,v).apply()}}
        text(16f).text=getString(R.string.rd_m10_channel)
        val channels=RadioGroup(this).apply{orientation=RadioGroup.VERTICAL};channelButtons=channels
        val stable=RadioButton(this).apply{id=View.generateViewId();setText(R.string.rd_m10_stable);minHeight=dp(48)}
        val beta=RadioButton(this).apply{id=View.generateViewId();setText(R.string.rd_m10_beta);minHeight=dp(48)}
        channels.addView(stable);channels.addView(beta);channels.check(if(RdUpdateCheck.channel(this)=="beta")beta.id else stable.id)
        channels.setOnCheckedChangeListener{_,id->prefs.edit().putString(RdUpdateCheck.KEY_CHANNEL,if(id==beta.id)"beta" else "stable").apply();found=null;checked=false;checkError=null;render()}
        layout.addView(channels)
        button(android.R.string.cancel){finish()}
        setContentView(ScrollView(this).apply{isFillViewport=true;addView(layout)})
        render();check.requestFocus()
        lifecycleScope.launch {
            withContext(Dispatchers.IO) {
                installed=runCatching{InstalledIdentity.current(applicationContext)}.getOrNull()
                installedVersion=runCatching{packageManager.getPackageInfo(packageName,0).versionName?:""}.getOrDefault("")
                val s=UpdateState.snapshot(applicationContext)
                selectedNotes=s.id?.let{runCatching{UpdateState.load(applicationContext,it).notes}.getOrDefault("") }?:""
            }
            loadingIdentity=false;render()
            if(installed!=null && UpdateState.snapshot(this@UpdateActivity).phase in setOf(Phase.NONE,Phase.INSTALLED))checkNow()
        }
    }
    private fun dp(n:Int)=(n*resources.displayMetrics.density+.5f).toInt()
    override fun onResume(){super.onResume();lifecycleScope.launch(Dispatchers.IO){UpdateState.reconcile(applicationContext)};handler.post(ticker)}
    override fun onPause(){handler.removeCallbacks(ticker);super.onPause()}
    private fun checkNow(){if(checking||loadingIdentity||installed==null)return;checking=true;checkError=null;found=null;render()
        lifecycleScope.launch{try{found=RdUpdateCheck.check(this@UpdateActivity,false);checked=true}
            catch(e:CancellationException){throw e}
            catch(e:HttpFailure){checkError=if(e.status==429 || (e.status==403 && e.remaining?.trim()=="0"))
                getString(R.string.rd_update_rate_limited) else getString(R.string.rd_update_unexpected,e.status.toString())}
            catch(e:java.io.IOException){checkError=getString(R.string.rd_update_offline)}
            catch(e:Exception){checkError=getString(R.string.rd_m10_security_error)}
            finally{checking=false;render()}}
    }
    private fun render(){if(!::info.isInitialized)return
        val s=UpdateState.snapshot(this);val m=found
        val active=s.phase !in setOf(Phase.NONE,Phase.INSTALLED)
        val header=if(loadingIdentity) getString(R.string.rd_update_checking) else installed?.let{getString(R.string.rd_m10_installed,it.edition,it.abi,installedVersion)}?:getString(R.string.rd_m10_unsupported)
        val line=when(s.phase){
            Phase.QUEUED->getString(R.string.rd_m10_queued)
            Phase.DOWNLOADING->getString(R.string.rd_m10_downloading)
            Phase.PAUSED->getString(R.string.rd_m10_paused)
            Phase.FAILED->getString(R.string.rd_m10_failed)
            Phase.READY->getString(if(s.error!=null)R.string.rd_m10_install_failed else R.string.rd_m10_ready)
            Phase.INSTALLING->getString(R.string.rd_m10_installing)
            Phase.CONFIRM->getString(R.string.rd_m10_confirm)
            Phase.NONE,Phase.INSTALLED->when{checking->getString(R.string.rd_update_checking);checkError!=null->checkError!!;m!=null->getString(R.string.rd_update_available,m.version);checked->getString(R.string.rd_update_latest);s.phase==Phase.INSTALLED->getString(R.string.rd_m10_installed_ok,s.version);else->""}
        }
        val bytes=s.id?.let{if(s.phase in setOf(Phase.READY,Phase.INSTALLING,Phase.CONFIRM))UpdateState.apk(this,it).length() else UpdateState.partial(this,it).length()}?:0L
        val status=header+"\n"+line+if(active&&s.size>0)"\n"+getString(R.string.rd_m10_bytes,bytes/1048576L,s.size/1048576L) else ""
        if(info.text.toString()!=status)info.text=status
        progress.visibility=if(active&&s.size>0)View.VISIBLE else View.GONE;progress.progress=if(s.size>0)((bytes.coerceIn(0,s.size)*1000)/s.size).toInt() else 0
        val noteText=if(!active)m?.notes?:"" else selectedNotes;if(notes.text.toString()!=noteText)notes.text=noteText;notes.visibility=if(notes.text.isNotEmpty())View.VISIBLE else View.GONE
        check.isEnabled=!checking&&!active&&installed!=null&&!loadingIdentity
        for(i in 0 until channelButtons.childCount)channelButtons.getChildAt(i).isEnabled=!active&&!checking&&!loadingIdentity
        val action=when(s.phase){Phase.NONE,Phase.INSTALLED->if(m!=null)R.string.download else null;Phase.PAUSED,Phase.FAILED->R.string.rd_m10_resume;Phase.QUEUED,Phase.DOWNLOADING->R.string.rd_m10_pause;Phase.READY->R.string.rd_m10_install;Phase.CONFIRM->R.string.rd_m10_confirm_action;Phase.INSTALLING->null}
        primary.visibility=if(action!=null)View.VISIBLE else View.GONE;action?.let{primary.setText(it)};primary.isEnabled=!installing&&!checking
        secondary.visibility=if(active)View.VISIBLE else View.GONE;secondary.isEnabled=!installing
    }
    private fun primaryAction(){val s=UpdateState.snapshot(this)
        when(s.phase){
            Phase.NONE,Phase.INSTALLED->{val m=found?:return;try{val id=UpdateState.select(this,m);selectedNotes=m.notes;found=null;UpdateJobs.resume(this,id)}catch(e:Exception){checkError=getString(R.string.rd_m10_failed);render()}}
            Phase.QUEUED,Phase.DOWNLOADING->s.id?.let{UpdateJobs.pause(this,it)}
            Phase.PAUSED,Phase.FAILED->s.id?.let{UpdateJobs.resume(this,it)}
            Phase.READY->{val id=s.id?:return;if(!UpdateInstaller.canInstall(this)){if(Build.VERSION.SDK_INT>=26)try{startActivity(Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:$packageName")))}catch(e:Exception){Toast.makeText(this,R.string.rd_m10_permission,Toast.LENGTH_LONG).show()};return}
                installing=true;lifecycleScope.launch{try{withContext(Dispatchers.IO){UpdateInstaller.install(applicationContext,id)}}catch(e:CancellationException){throw e}catch(e:Exception){Toast.makeText(this@UpdateActivity,R.string.rd_m10_install_failed,Toast.LENGTH_LONG).show()}finally{installing=false;render()}}}
            Phase.CONFIRM->{val confirmation=UpdateInstaller.confirmation(this,s.session);if(confirmation!=null)try{confirmation.send()}catch(e:Exception){Toast.makeText(this,R.string.rd_m10_confirmation_lost,Toast.LENGTH_LONG).show()}else Toast.makeText(this,R.string.rd_m10_confirmation_lost,Toast.LENGTH_LONG).show()}
            Phase.INSTALLING->Unit
        };render()
    }
    private fun secondaryAction(){val s=UpdateState.snapshot(this);val id=s.id?:return
        androidx.appcompat.app.AlertDialog.Builder(this).setMessage(R.string.rd_m10_cancel_question).setNegativeButton(android.R.string.no,null).setPositiveButton(android.R.string.yes){_,_->
            lifecycleScope.launch {
                withContext(Dispatchers.IO) { if(s.phase in setOf(Phase.CONFIRM,Phase.INSTALLING))UpdateInstaller.abandon(applicationContext,id) else UpdateJobs.discard(applicationContext,id) }
                found=null;checked=false;render()
            }}.show()}
}
