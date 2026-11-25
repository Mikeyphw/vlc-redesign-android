/* SPDX-License-Identifier: GPL-2.0-or-later */
package org.videolan.vlc.rd.updater

import java.net.URL
import android.net.Network
import java.net.HttpURLConnection
import javax.net.ssl.HttpsURLConnection
import java.io.ByteArrayOutputStream
import org.videolan.vlc.util.RdTls

internal class HttpFailure(val status: Int, val remaining: String?, val reset: String?) : java.io.IOException("HTTP $status")
internal object UpdateHttp {
    private val allowed = setOf("api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com")
    private fun checked(url: URL) { require(url.protocol == "https" && url.host.lowercase(java.util.Locale.ROOT) in allowed && url.userInfo == null && url.port in listOf(-1,443)) { "Untrusted update URL" } }
    fun open(initial: String, range: Long = 0, network: Network? = null): HttpsURLConnection {
        var url=URL(initial)
        repeat(6) {
            checked(url)
            val c=(network?.openConnection(url) ?: url.openConnection()) as HttpsURLConnection
            RdTls.apply(c)
            c.instanceFollowRedirects=false; c.connectTimeout=15000; c.readTimeout=30000
            c.setRequestProperty("User-Agent","VLC-Redesign-Android-Updater/1")
            c.setRequestProperty("Accept-Encoding","identity")
            if(url.host=="api.github.com") c.setRequestProperty("Accept","application/vnd.github+json")
            if(range>0)c.setRequestProperty("Range","bytes=$range-")
            try {
                val status=c.responseCode
                if(status in setOf(301,302,303,307,308)) {
                    val next=c.getHeaderField("Location") ?: error("Missing redirect")
                    url=URL(url,next); c.disconnect()
                } else if(status in setOf(HttpURLConnection.HTTP_OK,HttpURLConnection.HTTP_PARTIAL)) return c
                else throw HttpFailure(status,c.getHeaderField("x-ratelimit-remaining"),c.getHeaderField("x-ratelimit-reset"))
            } catch(t:Throwable){c.disconnect();throw t}
        }
        error("Too many redirects")
    }
    fun read(url: String, max: Int): ByteArray {
        val c=open(url)
        try {
            require(c.responseCode==200)
            val out=ByteArrayOutputStream()
            c.inputStream.use { input -> val buf=ByteArray(8192); while(true){val n=input.read(buf);if(n<0) break; require(out.size()+n<=max){"Update metadata too large"};out.write(buf,0,n)} }
            return out.toByteArray()
        } finally {c.disconnect()}
    }
}
