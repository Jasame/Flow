# Kotlin and AndroidX ship their own rules. Nothing here is reached through reflection except the receivers and the
# service named in the manifest, which R8 keeps by itself.
-dontwarn org.checkerframework.**
-dontwarn com.google.errorprone.annotations.**
