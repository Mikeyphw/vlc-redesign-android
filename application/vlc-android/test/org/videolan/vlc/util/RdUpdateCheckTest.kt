/* SPDX-License-Identifier: GPL-2.0-or-later */
package org.videolan.vlc.util

import org.junit.Test
import org.junit.Assert.*
import org.videolan.vlc.rd.updater.UpdateTrust

class RdUpdateCheckTest {
    @Test fun identitiesAreExact() {
        assertEquals("standalone",UpdateTrust.edition("com.mikeyphw.vlcredesign"))
        assertEquals("original",UpdateTrust.edition("org.videolan.vlc"))
        assertNull(UpdateTrust.edition("org.kuchisoft.vlc"))
        assertNull(UpdateTrust.edition("com.mikeyphw.vlcredesign.debug"))
    }
    @Test fun versionsAreMonotonicForEachAbi() {
        for(abi in UpdateTrust.abiCodes.keys) {
            assertTrue(UpdateTrust.expectedCode("0.7.6",abi)>UpdateTrust.expectedCode("0.7.5",abi))
            assertTrue(UpdateTrust.expectedCode("0.10.0",abi)>UpdateTrust.expectedCode("0.9.99",abi))
        }
    }
    @Test fun wrongInputsFailClosed() {
        for(v in listOf("00.7.6","0.7.6-beta","0.7.100","11.0.0")) assertTrue(runCatching { UpdateTrust.expectedCode(v,"arm64-v8a") }.isFailure)
        assertTrue(runCatching { UpdateTrust.expectedCode("0.7.6","mips") }.isFailure)
        assertTrue(runCatching { UpdateTrust.assetUrl("v0.7.6","../bad") }.isFailure)
        assertTrue(runCatching { UpdateTrust.verifyManifest(byteArrayOf(1),byteArrayOf(2),byteArrayOf(3)) }.isFailure)
    }
    @Test fun canonicalReleaseLocation() {
        assertEquals("https://github.com/Mikeyphw/vlc-redesign-android/releases/download/v0.7.6/update-original.json",UpdateTrust.assetUrl(UpdateTrust.tag("0.7.6","stable"),"update-original.json"))
        assertEquals("v0.7.6-beta",UpdateTrust.tag("0.7.6","beta"))
    }
}
