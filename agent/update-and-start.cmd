@echo off
setlocal
cd /d "%~dp0"
py -c "import hashlib,os,pathlib,runpy,urllib.request; p=pathlib.Path('code')/'launcher.py'; p.parent.mkdir(exist_ok=True); u='https://raw.githubusercontent.com/chi-pao/venture-agent-sites/7d7de7f4e14136991e60eaf92b22ec0dd71f9e33/agent/launcher.py'; h='7e8bf0eaac58abfd77ba4f7a16459108e93b1c5a7834680ba851f99b049ddd18'; exec('try:\n s=urllib.request.urlopen(u,timeout=20).read(100000)\n if hashlib.sha256(s).hexdigest()!=h: raise ValueError(\"Launcher checksum mismatch\")\n t=p.with_suffix(\".tmp\"); t.write_bytes(s); os.replace(t,p)\nexcept Exception:\n if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=h: raise\n'); runpy.run_path(str(p),run_name='__main__')" --data-home "%~dp0." %*
if errorlevel 1 pause
endlocal
