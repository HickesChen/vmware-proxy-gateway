# Third-party offline components

The files below are redistributed unchanged for offline installation. They are not covered by this repository's MIT license.

- `sing-box/1.10.7/`: sing-box 1.10.7 from <https://github.com/SagerNet/sing-box/releases/tag/v1.10.7>, licensed GPL-3.0-or-later. Corresponding source: <https://github.com/SagerNet/sing-box/tree/v1.10.7>.
- `python/pystray-0.19.5-*.whl`: pystray 0.19.5 from <https://pypi.org/project/pystray/0.19.5/>, licensed LGPL-3.0.
- Other files under `python/`: the python-xlib and six wheels required by pystray. Their package metadata contains their respective license and project information. Pillow is supplied by the Ubuntu Desktop `python3-pil` package and is intentionally not duplicated here.
- `debs/<codename>/<arch>/`: unmodified Ubuntu binary packages downloaded from the configured Ubuntu archive. Package copyright and license files are installed under `/usr/share/doc/<package>/copyright`; corresponding source packages are available from <https://packages.ubuntu.com/> and the configured Ubuntu archive.

`SHA256SUMS` records the exact contents used by the offline installer. Regenerate the bundle and manifest together with `tools/prepare_offline_bundle.sh`.
