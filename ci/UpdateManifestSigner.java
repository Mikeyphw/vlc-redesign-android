/* SPDX-License-Identifier: GPL-2.0-or-later */
import java.nio.file.*;
import java.io.*;
import java.security.*;
import java.security.cert.*;
import java.util.*;

/** Signs exact release-manifest bytes with the same approved key as the APK. */
public final class UpdateManifestSigner {
    static String env(String name) {
        String value = System.getenv(name);
        if (value == null || value.isEmpty()) throw new IllegalArgumentException("missing " + name);
        return value;
    }
    static String fingerprint(java.security.cert.Certificate cert) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(cert.getEncoded()));
    }
    static String algorithm(Key key) {
        if (key.getAlgorithm().equalsIgnoreCase("RSA")) return "SHA256withRSA";
        if (key.getAlgorithm().equalsIgnoreCase("EC")) return "SHA256withECDSA";
        throw new IllegalArgumentException("unsupported release signer key type");
    }
    static byte[] input(Path file, long max) throws IOException {
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || Files.size(file) > max) throw new IOException("invalid input file");
        return Files.readAllBytes(file);
    }
    static void verify(byte[] payload, byte[] signature, java.security.cert.Certificate certificate, String expected) throws Exception {
        if (!fingerprint(certificate).equals(expected)) throw new SecurityException("certificate identity mismatch");
        Signature verifier = Signature.getInstance(algorithm(certificate.getPublicKey()));
        verifier.initVerify(certificate);
        verifier.update(payload);
        if (!verifier.verify(signature)) throw new SecurityException("manifest signature invalid");
    }
    public static void main(String[] args) {
        char[] storePassword = null, keyPassword = null;
        try {
            if (args.length != 5) throw new IllegalArgumentException("sign|verify manifest signature cert expected-cert-sha256");
            Path manifest = Path.of(args[1]), signaturePath = Path.of(args[2]), certPath = Path.of(args[3]);
            String expected = args[4];
            if (!expected.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("invalid expected cert SHA256");
            byte[] payload = input(manifest, 262144);
            if (args[0].equals("sign")) {
                storePassword = env("RD_KEYSTORE_PASSWORD").toCharArray();
                keyPassword = env("RD_KEY_PASSWORD").toCharArray();
                KeyStore store = KeyStore.getInstance(new File(env("RD_KEYSTORE_FILE")), storePassword);
                String alias = env("RD_KEY_ALIAS");
                Key key = store.getKey(alias, keyPassword);
                java.security.cert.Certificate cert = store.getCertificate(alias);
                if (!(key instanceof PrivateKey) || cert == null || !fingerprint(cert).equals(expected)) throw new SecurityException("approved signing identity not available");
                Signature signer = Signature.getInstance(algorithm(key));
                signer.initSign((PrivateKey) key);
                signer.update(payload);
                byte[] signature = signer.sign();
                verify(payload, signature, cert, expected);
                Files.write(signaturePath, signature, StandardOpenOption.CREATE_NEW);
                Files.write(certPath, cert.getEncoded(), StandardOpenOption.CREATE_NEW);
            } else if (args[0].equals("verify")) {
                java.security.cert.Certificate cert = CertificateFactory.getInstance("X.509").generateCertificate(new ByteArrayInputStream(input(certPath, 65536)));
                verify(payload, input(signaturePath, 16384), cert, expected);
            } else throw new IllegalArgumentException("unknown operation");
            System.out.println("UPDATE_MANIFEST_SIGNATURE_VERIFIED");
        } catch (Exception e) {
            // Never expose key material, credentials, or keystore provider exception details.
            System.err.println("UPDATE_MANIFEST_REFUSED: " + e.getClass().getSimpleName());
            System.exit(2);
        } finally {
            if (storePassword != null) Arrays.fill(storePassword, '\0');
            if (keyPassword != null) Arrays.fill(keyPassword, '\0');
        }
    }
}
