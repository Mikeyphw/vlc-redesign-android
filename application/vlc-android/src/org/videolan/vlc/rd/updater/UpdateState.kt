/* SPDX-License-Identifier: GPL-2.0-or-later */
package org.videolan.vlc.rd.updater

import android.content.Context
import java.io.File
import java.util.UUID

internal enum class Phase { NONE, QUEUED, DOWNLOADING, PAUSED, READY, FAILED, INSTALLING, CONFIRM, INSTALLED }
internal data class UpdateSnapshot(val id:String?,val phase:Phase,val version:String,val size:Long,val session:Int,val error:String?)
internal object UpdateState {
    private val mutex=Any()
    fun prefs(c:Context)=c.getSharedPreferences("rd_fork_update_state_v1",Context.MODE_PRIVATE)
    fun root(c:Context)=File(c.noBackupFilesDir,"rd-fork-updater-v1").apply{if(!isDirectory)check(mkdirs() || isDirectory)}
    fun folder(c:Context,id:String):File{require(Regex("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}").matches(id));return File(root(c),id)}
    fun apk(c:Context,id:String)=File(folder(c,id),"update.apk")
    fun partial(c:Context,id:String)=File(folder(c,id),"update.part")
    fun snapshot(c:Context):UpdateSnapshot=synchronized(mutex){val p=prefs(c);UpdateSnapshot(p.getString("id",null),Phase.values().firstOrNull{it.name==p.getString("phase",null)}?:Phase.NONE,p.getString("version","")?:"",p.getLong("size",0),p.getInt("session",-1),p.getString("error",null))}
    fun select(c:Context,m:UpdateManifest):String=synchronized(mutex){
        val old=snapshot(c);require(old.phase !in setOf(Phase.QUEUED,Phase.DOWNLOADING,Phase.INSTALLING,Phase.CONFIRM)){"An update is active"}
        val id=UUID.randomUUID().toString();val dir=folder(c,id);check(dir.mkdir());
        try {File(dir,"manifest.json").writeBytes(m.payload);File(dir,"manifest.sig").writeBytes(m.signature)
            check(prefs(c).edit().clear().putString("id",id).putString("phase",Phase.PAUSED.name).putString("version",m.version).putLong("size",m.asset.size).putLong("version_code",m.asset.code).putString("signer",m.signer).putString("apk_sha256",m.asset.sha256).commit())
        }catch(e:Exception){dir.deleteRecursively();throw e}
        old.id?.let{folder(c,it).deleteRecursively()};id
    }
    fun load(c:Context,id:String):UpdateManifest {
        require(snapshot(c).id==id){"Stale update"};val dir=folder(c,id)
        val body=File(dir,"manifest.json");val sig=File(dir,"manifest.sig")
        require(body.length() in 1..UpdateTrust.MAX_MANIFEST.toLong()&&sig.length() in 1..16384)
        return UpdateManifest.parse(body.readBytes(),sig.readBytes(),InstalledIdentity.current(c))
    }
    fun transition(c:Context,id:String,from:Set<Phase>,to:Phase,error:String?=null,session:Int?=null):Boolean=synchronized(mutex){
        val s=snapshot(c);if(s.id!=id||s.phase !in from)return@synchronized false
        val e=prefs(c).edit().putString("phase",to.name).putString("error",error);session?.let{e.putInt("session",it)};check(e.commit());true
    }
    fun resetRetries(c:Context,id:String) = synchronized(mutex) {
        if(snapshot(c).id==id) check(prefs(c).edit().putInt("retry_count",0).commit())
    }
    fun recordRetry(c:Context,id:String):Int = synchronized(mutex) {
        if(snapshot(c).id!=id) return@synchronized UpdateTrust.MAX_RETRIES
        val n=prefs(c).getInt("retry_count",0)+1
        check(prefs(c).edit().putInt("retry_count",n).commit());n
    }
    fun discard(c:Context,id:String):Boolean=synchronized(mutex){val s=snapshot(c);if(s.id!=id||s.phase in setOf(Phase.INSTALLING,Phase.CONFIRM))return@synchronized false;check(prefs(c).edit().clear().commit());folder(c,id).deleteRecursively();true}
    fun reconcile(c:Context) = UpdateInstaller.withInstallLock { reconcileLocked(c) }
    private fun reconcileLocked(c:Context) {
        val s=snapshot(c);val id=s.id?:return
        if (s.phase == Phase.INSTALLED) return
        val installed=runCatching{InstalledIdentity.current(c)}.getOrNull()?:return
        val target=prefs(c).getLong("version_code",Long.MAX_VALUE)
        if(installed.code==target && UpdateTrust.digest(installed.certificate)==prefs(c).getString("signer",null)) {
            val actual=runCatching { InstalledIdentity.fileDigest(File(c.applicationInfo.sourceDir)) }.getOrNull()
            if(actual==prefs(c).getString("apk_sha256",null) && actual!=null) {
                if(s.phase!=Phase.INSTALLED && transition(c,id,Phase.values().toSet(),Phase.INSTALLED,session=-1)) folder(c,id).deleteRecursively()
            } else if(s.phase!=Phase.INSTALLED) transition(c,id,Phase.values().toSet(),Phase.FAILED,"installed_identity_unverified",-1)
        } else if(installed.code>target) {
            if(transition(c,id,Phase.values().toSet(),Phase.FAILED,"superseded",-1)) discard(c,id)
        } else if(s.phase==Phase.INSTALLING && s.session<0) {
            // An interrupted pre-commit operation is not proof of installation. Do not replay a session.
            transition(c,id,setOf(Phase.INSTALLING),Phase.READY,"install_incomplete",-1)
        }
        else if(s.phase in setOf(Phase.INSTALLING,Phase.CONFIRM) && s.session>=0 && c.packageManager.packageInstaller.getSessionInfo(s.session)==null) {
            transition(c,id,setOf(Phase.INSTALLING,Phase.CONFIRM),Phase.READY,"install_incomplete",-1)
        }
    }
}
