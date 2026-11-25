/* SPDX-License-Identifier: GPL-2.0-or-later */
package org.videolan.vlc.rd.updater

import java.security.MessageDigest
import java.security.Signature
import java.security.cert.CertificateFactory

/** Shared cryptographic policy, independent of Android lifecycle and network APIs. */
object UpdateTrust {
    const val REPOSITORY = "Mikeyphw/vlc-redesign-android"
    const val MAX_MANIFEST = 262144
    const val MAX_RETRIES = 5
    fun retryableHttp(status:Int) = status == 408 || status == 429 || status in 500..599
    const val MAX_APK = 512L * 1024 * 1024
    val identities = mapOf("standalone" to "com.mikeyphw.vlcredesign", "original" to "org.videolan.vlc")
    val abiCodes = mapOf("armeabi-v7a" to 5, "arm64-v8a" to 6, "x86" to 7, "x86_64" to 8)
    private val hex64 = Regex("[0-9a-f]{64}")
    private val numericVersion = Regex("(?:0|[1-9][0-9]?)\\.(?:0|[1-9][0-9]?)\\.(?:0|[1-9][0-9]?)")
    fun digest(bytes: ByteArray): String = hex(MessageDigest.getInstance("SHA-256").digest(bytes))
    fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(java.util.Locale.ROOT, it.toInt() and 255) }
    fun isDigest(s: String) = hex64.matches(s)
    fun edition(packageName: String) = identities.entries.singleOrNull { it.value == packageName }?.key
    fun expectedCode(version: String, abi: String): Long {
        require(numericVersion.matches(version)) { "Invalid version" }
        val (major, minor, patch) = version.split('.').map { it.toLong() }
        require(major <= 10 && minor < 100 && patch < 100) { "Invalid version" }
        return 10000000 + 3100000 + 10 * (major * 10000 + minor * 100 + patch) + (abiCodes[abi] ?: error("Unknown ABI"))
    }
    fun verifyManifest(payload: ByteArray, signature: ByteArray, installedCertificate: ByteArray): String {
        require(payload.isNotEmpty() && payload.size <= MAX_MANIFEST && signature.isNotEmpty() && signature.size <= 16384)
        val cert = CertificateFactory.getInstance("X.509").generateCertificate(installedCertificate.inputStream())
        val algo = when (cert.publicKey.algorithm) { "RSA" -> "SHA256withRSA"; "EC" -> "SHA256withECDSA"; else -> error("Unsupported signer") }
        val verifier = Signature.getInstance(algo)
        verifier.initVerify(cert.publicKey); verifier.update(payload)
        if (!verifier.verify(signature)) throw SecurityException("Manifest signature does not match installed release")
        return digest(cert.encoded)
    }
    fun assetName(edition: String, version: String, abi: String): String {
        require(edition in identities && numericVersion.matches(version) && abi in abiCodes)
        return "VLC-Redesign-$edition-$version-$abi.apk"
    }
    fun tag(version: String, channel: String): String {
        require(numericVersion.matches(version) && channel in setOf("stable", "beta"))
        return "v$version" + if (channel == "beta") "-beta" else ""
    }
    fun assetUrl(tag: String, name: String): String {
        require(Regex("v[0-9]{1,3}\\.[0-9]{1,2}\\.[0-9]{1,2}(-beta)?").matches(tag))
        require(Regex("[A-Za-z0-9_.-]{1,128}").matches(name) && name != "." && name != "..")
        return "https://github.com/$REPOSITORY/releases/download/$tag/$name"
    }
}
