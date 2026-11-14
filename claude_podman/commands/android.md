Android work in the sandbox. Use $ARGUMENTS for the specific task.

What the sandbox can do: a CLI Gradle build (`./gradlew assembleDebug`,
unit tests that run on the JVM, lint). Keep Gradle's cache and build
output out of the shared tree (see the sandbox rules, "Files shared
with the host"): set `GRADLE_USER_HOME` and the build directory under
`.claude-data/var/cache/`.

What it can't do: emulator, device, instrumented tests, UI checks.
Anything that needs them is unverifiable here: mark the task `[~]` and
say exactly what to check on the host (sandbox rules, "Host
verification"). In `tasks` output, tag them `(host verify: Android
device/emulator)`.
