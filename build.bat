py -m pip install -U --pre "yt-dlp[default]"
py -m pip install -U --pre pyinstaller
py devscripts/install_deps.py --include pyinstaller
py devscripts/make_lazy_extractors.py
py -m bundle.pyinstaller