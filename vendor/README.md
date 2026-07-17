# Offline dependency bundle

This directory is populated on a connected Ubuntu build machine with:

```bash
tools/prepare_offline_bundle.sh
```

The generated layout is versioned by Ubuntu codename and architecture:

```text
vendor/debs/<codename>/<arch>/*.deb
vendor/python/*.whl
vendor/sing-box/<version>/linux-<arch>/sing-box
vendor/SHA256SUMS
```

Include the populated directory in the source or release archive. The target VM can then install without network access using `sudo ./install.sh --offline`.

Normal installation uses this bundle without network access when the platform matches. On another Ubuntu version or architecture it may download only missing OS packages and sing-box; `install.sh --offline` disables that fallback. Python wheels are always extracted into the application's private `vendor-python` directory with Python's standard library, so pip, setuptools, and wheel are not required on the target or by the normal bundle-preparation workflow.

The three pure-Python wheels under `vendor/python/` are committed, pinned application resources. `prepare_offline_bundle.sh` verifies them but never contacts PyPI or replaces them. Updating those libraries is a separate deliberate dependency-upgrade task.

The bundle intentionally excludes components supplied by the supported Ubuntu Desktop Minimal base system, including Bash/coreutils, Python 3, systemd, APT/dpkg, iproute2, GTK/Tk, CA certificates, archive tools, libc, and standard fonts. It contains only application-added packages and dependencies not already in that baseline.
