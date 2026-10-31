@echo off
setlocal
cd /d "%~dp0"
py -c "import hashlib,os,pathlib,runpy,urllib.request; p=pathlib.Path('code')/'launcher.py'; p.parent.mkdir(exist_ok=True); u='https://raw.githubusercontent.com/chi-pao/venture-agent-sites/a20b8eccf3148ba56783c347985c4f8544b60708/agent/launcher.py'; h='d515132b339246ef8170b98d06c55463a3121e2c94c8791738538d352d87ba8d'; exec('try:\n s=urllib.request.urlopen(u,timeout=20).read(100000)\n if hashlib.sha256(s).hexdigest()!=h: raise ValueError(\"Launcher checksum mismatch\")\n t=p.with_suffix(\".tmp\"); t.write_bytes(s); os.replace(t,p)\nexcept Exception:\n if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=h: raise\n'); runpy.run_path(str(p),run_name='__main__')" --data-home "%~dp0." %*
if errorlevel 1 pause
endlocal
