/* SPDX-License-Identifier: GPL-2.0-or-later */
package org.videolan.vlc.rd.updater

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import org.json.JSONObject
import java.io.File
import java.util.zip.ZipFile

internal data class InstalledRelease(val packageName: String, val edition: String, val abi: String, val code: Long, val certificate: ByteArray)
internal data class UpdateAsset(val abi: String, val file: String, val code: Long, val sha256: String, val size: Long, val minSdk: Int)
internal data class UpdateManifest(val edition: String, val packageName: String, val version: String, val channel: String,
    val sourceCommit: String, val notes: String, val signer: String, val asset: UpdateAsset,
    val tag: String, val payload: ByteArray, val signature: ByteArray) {
    val url get() = UpdateTrust.assetUrl(tag, asset.file)
    companion object {
        fun parse(payload: ByteArray, signature: ByteArray, installed: InstalledRelease): UpdateManifest {
            val signer = UpdateTrust.verifyManifest(payload, signature, installed.certificate)
            val json = JSONObject(payload.toString(Charsets.UTF_8))
            require(json.getInt("schema") == 1 && json.getString("repository") == UpdateTrust.REPOSITORY)
            require(json.getString("packageName") == installed.packageName && json.getString("edition") == installed.edition)
            require(json.getString("signingCertificateSha256") == signer)
            val version = json.getString("versionName"); val channel = json.getString("channel")
            val tag = UpdateTrust.tag(version, channel)
            val source = json.getString("sourceCommit"); require(Regex("[0-9a-f]{40}").matches(source))
            val notes = json.getString("notes"); require(notes.toByteArray().size <= 65536)
            val entries = json.getJSONArray("assets"); require(entries.length() == UpdateTrust.abiCodes.size)
            val found = mutableMapOf<String, UpdateAsset>()
            for (i in 0 until entries.length()) {
                val a = entries.getJSONObject(i); val abi = a.getString("abi")
                val file = a.getString("file"); val code = a.getLong("versionCode"); val hash = a.getString("sha256")
                val size = a.getLong("size"); val sdk = a.getInt("minSdk")
                require(file == UpdateTrust.assetName(installed.edition, version, abi) && code == UpdateTrust.expectedCode(version, abi))
                require(UpdateTrust.isDigest(hash) && size in 1..UpdateTrust.MAX_APK && sdk == 21)
                require(found.put(abi, UpdateAsset(abi,file,code,hash,size,sdk)) == null)
            }
            require(found.keys == UpdateTrust.abiCodes.keys)
            val asset = found.getValue(installed.abi); require(asset.minSdk <= Build.VERSION.SDK_INT)
            return UpdateManifest(installed.edition, installed.packageName, version, channel, source, notes, signer, asset, tag, payload, signature)
        }
    }
}

@Suppress("DEPRECATION")
internal object InstalledIdentity {
    private val flags get() = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
    fun certificate(info: PackageInfo): ByteArray {
        val signatures = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners else info.signatures
        require(signatures?.size == 1) { "Unsupported signing identity" }
        return signatures!![0].toByteArray()
    }
    fun version(info: PackageInfo) = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()
    fun nativeAbis(file: File): Set<String> = ZipFile(file).use { zip ->
        zip.entries().asSequence().filter { !it.isDirectory && it.name.startsWith("lib/") && it.name.endsWith(".so") }
            .map { it.name.split('/')[1] }.toSet()
    }
    fun current(context: Context): InstalledRelease {
        val pkg = context.packageName; val edition = UpdateTrust.edition(pkg) ?: error("Not a supported release edition")
        val info = context.packageManager.getPackageInfo(pkg, flags)
        val available = nativeAbis(File(context.applicationInfo.sourceDir))
        val supported = Build.SUPPORTED_ABIS.toList()
        // Never change architecture in an in-place update; a multi-ABI development APK is not a production edition.
        val abi = available.singleOrNull()?.takeIf { it in UpdateTrust.abiCodes && it in supported } ?: error("Unsupported installed ABI")
        return InstalledRelease(pkg,edition,abi,version(info),certificate(info))
    }
    fun fileDigest(file: File):String {
        val digest=java.security.MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered().use { input -> val buf=ByteArray(65536); while(true){val n=input.read(buf);if(n<0)break;digest.update(buf,0,n)} }
        return UpdateTrust.hex(digest.digest())
    }
    fun verifyApk(context: Context, apk: File, manifest: UpdateManifest) {
        val installed = current(context)
        require(installed.packageName == manifest.packageName && installed.abi == manifest.asset.abi && installed.code < manifest.asset.code)
        require(UpdateTrust.digest(installed.certificate) == manifest.signer)
        require(apk.isFile && apk.length() == manifest.asset.size)
        require(fileDigest(apk) == manifest.asset.sha256) { "APK digest mismatch" }
        val archive = context.packageManager.getPackageArchiveInfo(apk.absolutePath, flags) ?: error("Invalid APK")
        require(archive.packageName == installed.packageName && version(archive) == manifest.asset.code)
        require(certificate(archive).contentEquals(installed.certificate)) { "APK signer mismatch" }
        require(nativeAbis(apk) == setOf(installed.abi)) { "APK ABI mismatch" }
    }
}
