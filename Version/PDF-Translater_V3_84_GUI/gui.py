#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess, threading, queue, tempfile, os, sys, json, re, urllib.request
import contextlib, io, traceback, importlib, shutil as _shutil, time, webbrowser, base64
from pathlib import Path

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ENGINE = APP_DIR / "translate_pdf.py"
PORT = 13305

# 사용자 설정(API 키 등) 저장 위치 - 실행파일 위치와 무관하게 항상 같은 곳을 사용
CONFIG_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "PDFTranslaterGUI"
CONFIG_PATH = CONFIG_DIR / "config.json"

# 언어 콤보박스 프리셋 (자유 입력도 가능 - 콤보박스가 readonly가 아님)
SOURCE_LANG_OPTIONS = ["English", "자동 인식", "한국어", "Japanese", "Chinese (Simplified)",
                       "French", "German", "Spanish"]
TARGET_LANG_OPTIONS = ["한국어", "English", "Japanese", "Chinese (Simplified)",
                       "French", "German", "Spanish"]
# GUI 표시용 '자동 인식'을 엔진이 이해하는 sentinel로 변환 (engine.resolve_source_lang과 짝)
AUTO_DETECT_LABEL = "자동 인식"
AUTO_DETECT_SENTINEL = "auto"

# Windows에서 서브프로세스가 부모(windowed EXE)와 별도로 콘솔 창을 새로 띄우는 것을 막는 플래그.
# --windowed로 빌드해도 이 플래그 없이 subprocess를 부르면 자식 프로세스용 콘솔이 반짝 뜰 수 있다.
_NOWIN = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

def _real_python_candidates():
    found=[]
    if os.name=="nt":
        try:
            p=subprocess.check_output(["py","-3.12","-c","import sys;print(sys.executable)"],
                                      text=True,stderr=subprocess.DEVNULL,creationflags=_NOWIN).strip()
            if p and Path(p).is_file(): found.append(p)
        except Exception: pass
        fallback=Path(os.environ.get("LOCALAPPDATA",""))/"Programs"/"Python"/"Python312"/"python.exe"
        if fallback.is_file() and str(fallback) not in found: found.append(str(fallback))
    if "WindowsApps" not in str(sys.executable) and Path(sys.executable).is_file():
        found.append(sys.executable)
    return found

def _has_pymupdf(python_exe):
    try:
        return subprocess.run([python_exe,"-c","import pymupdf"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,
            creationflags=_NOWIN).returncode==0
    except Exception:return False

def _double_click_bootstrap():
    """
    .py 연결이 WindowsApps Python으로 잡혀 있어도 실제 Python 3.12로 재실행.
    os.execv 대신 subprocess.Popen 후 현재 프로세스를 종료해 Windows Store alias 문제를 피한다.
    """
    if getattr(sys,"frozen",False) or os.name!="nt" or "WindowsApps" not in str(sys.executable):
        return
    script=str(Path(__file__).resolve())
    for pyexe in _real_python_candidates():
        if "WindowsApps" not in pyexe and _has_pymupdf(pyexe):
            subprocess.Popen([pyexe,script,*sys.argv[1:]],cwd=str(Path(__file__).resolve().parent))
            raise SystemExit(0)

_double_click_bootstrap()

PRESETS={2:(450,2,3072),4:(1000,5,4096),8:(2500,16,6144)}
def bits(name):
    for p in (r'(?:^|[-_.])e([2-8])b(?:$|[-_.])',r'(?:^|[-_.])([2-8])b(?:$|[-_.])',r'(?:^|[-_.])q([2-8])(?:[_-]\d+)?(?:$|[-_.])',r'int([2-8])'):
        m=re.search(p,name,re.I)
        if m:return int(m.group(1))
    return 4
def preset(name):
    b=bits(name)
    if b in PRESETS:return PRESETS[b]
    lo=max(x for x in PRESETS if x<b); hi=min(x for x in PRESETS if x>b); t=(b-lo)/(hi-lo)
    return tuple(round(PRESETS[lo][i]+t*(PRESETS[hi][i]-PRESETS[lo][i])) for i in range(3))

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Translater v3.82")
        self.geometry("1000x820")
        self.minsize(850,650)
        self.q=queue.Queue(); self.proc=None; self.keyfile=None; self.engine_completed=False
        self.engine=None; self.start_time=None; self.pct=0.0
        self.inp=tk.StringVar(); self.out=tk.StringVar(); self.pages=tk.StringVar()
        self.src=tk.StringVar(value="English"); self.dst=tk.StringVar(value="한국어")
        self.model=tk.StringVar(value="gemma4-it-e2b-FLM")
        self.chars=tk.StringVar(); self.segs=tk.StringVar(); self.tokens=tk.StringVar()
        self.use_npu=tk.BooleanVar(value=True); self.api_rows=[]
        self.build()
        if not self.load_config():
            self.add_api("gemini"); self.add_api("anthropic"); self.add_api("openai")
        self.refresh_models(); self.after(100,self.poll)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def build(self):
        main=ttk.Frame(self,padding=10); main.pack(fill="both",expand=True)
        f=ttk.LabelFrame(main,text="PDF 파일"); f.pack(fill="x")
        for r,(label,var,save) in enumerate((("입력 PDF",self.inp,False),("출력 PDF (비우면 자동 이름)",self.out,True))):
            ttk.Label(f,text=label,width=23).grid(row=r,column=0,padx=5,pady=5,sticky="w")
            ttk.Entry(f,textvariable=var).grid(row=r,column=1,padx=5,pady=5,sticky="ew")
            ttk.Button(f,text="찾기",command=lambda v=var,s=save:self.pick(v,s)).grid(row=r,column=2,padx=5)
        f.columnconfigure(1,weight=1)

        o=ttk.LabelFrame(main,text="기본 설정"); o.pack(fill="x",pady=7)
        ttk.Label(o,text="페이지 범위").grid(row=0,column=0,padx=5,pady=6)
        ttk.Entry(o,textvariable=self.pages,width=20).grid(row=0,column=1,padx=5)
        ttk.Label(o,text="원문 언어").grid(row=0,column=2,padx=5,pady=6)
        ttk.Combobox(o,textvariable=self.src,values=SOURCE_LANG_OPTIONS,width=18).grid(row=0,column=3,padx=5)
        ttk.Label(o,text="번역 언어").grid(row=0,column=4,padx=5,pady=6)
        ttk.Combobox(o,textvariable=self.dst,values=TARGET_LANG_OPTIONS,width=18).grid(row=0,column=5,padx=5)

        a=ttk.LabelFrame(main,text="API 키 — 체크된 API만 사용"); a.pack(fill="x")
        self.api_frame=ttk.Frame(a); self.api_frame.pack(fill="x")
        api_buttons=ttk.Frame(a); api_buttons.pack(fill="x",padx=5,pady=4)
        ttk.Button(api_buttons,text="+ API 추가",command=lambda:self.add_api("gemini")).pack(side="left")
        ttk.Button(api_buttons,text="요구사항 설치",command=self.install_requirements).pack(side="left",padx=6)
        ttk.Button(api_buttons,text="필수사항 설치 (Python/Lemonade)",command=self.install_prerequisites).pack(side="left")

        n=ttk.LabelFrame(main,text="Lemonade NPU / 모델 설정"); n.pack(fill="x",pady=7)
        ttk.Checkbutton(n,text="로컬 NPU 사용",variable=self.use_npu).grid(row=0,column=0,padx=5)
        ttk.Label(n,text="모델").grid(row=0,column=1,padx=5)
        self.models=ttk.Combobox(n,textvariable=self.model,state="readonly",width=38)
        self.models.grid(row=0,column=2,padx=5); self.models.bind("<<ComboboxSelected>>",self.model_changed)
        ttk.Button(n,text="모델 새로고침",command=self.refresh_models).grid(row=0,column=3,padx=5)
        for i,(label,var) in enumerate((("배치 문자 수",self.chars),("세그먼트 수",self.segs),("max_tokens",self.tokens))):
            ttk.Label(n,text=label).grid(row=1,column=i*2,padx=5,pady=7)
            ttk.Entry(n,textvariable=var,width=15).grid(row=1,column=i*2+1,padx=5)

        self.status=tk.StringVar(value="대기 중")
        ttk.Label(main,textvariable=self.status).pack(anchor="w")
        self.prog_info=tk.StringVar(value="")
        ttk.Label(main,textvariable=self.prog_info,foreground="#555555").pack(anchor="w")
        self.progress=ttk.Progressbar(main,maximum=100); self.progress.pack(fill="x",pady=5)
        buttons=ttk.Frame(main); buttons.pack(fill="x")
        self.startbtn=ttk.Button(buttons,text="번역 시작",command=self.start); self.startbtn.pack(side="left")
        self.stopbtn=ttk.Button(buttons,text="중단 (진행분까지 저장)",command=self.stop,state="disabled")
        self.stopbtn.pack(side="left",padx=5)
        ttk.Button(buttons,text="로그 지우기",command=lambda:self.log.delete("1.0","end")).pack(side="right")
        self.log=tk.Text(main,height=25,wrap="word"); self.log.pack(fill="both",expand=True,pady=7)

    def add_api(self, provider):
        row=ttk.Frame(self.api_frame); row.pack(fill="x",padx=5,pady=2)
        on=tk.BooleanVar(value=False); pv=tk.StringVar(value=provider); key=tk.StringVar()
        ttk.Checkbutton(row,variable=on).pack(side="left")
        ttk.Combobox(row,textvariable=pv,values=("gemini","anthropic","openai"),state="readonly",width=12).pack(side="left",padx=4)
        ttk.Entry(row,textvariable=key,show="●").pack(side="left",fill="x",expand=True)
        item=[row,on,pv,key]
        ttk.Button(row,text="삭제",command=lambda:self.remove_api(item)).pack(side="left",padx=4)
        self.api_rows.append(item)
    def remove_api(self,item):
        item[0].destroy()
        if item in self.api_rows:self.api_rows.remove(item)

    # ------------------------------------------------------------------
    # 필수사항 설치: Python 3.12 -> Lemonade Server -> pip requirements 순차 진행
    # ------------------------------------------------------------------
    def _log(self,msg): self.q.put(("LOG",msg if msg.endswith("\n") else msg+"\n"))

    def _python312_ok(self):
        return any("WindowsApps" not in p for p in _real_python_candidates())

    def _lemonade_ok(self):
        try:
            with urllib.request.urlopen(f"http://localhost:{PORT}/api/v1/models",timeout=2):return True
        except Exception:pass
        bin_dir=Path(os.environ.get("LOCALAPPDATA",""))/"lemonade_server"/"bin"
        return (bin_dir/"LemonadeServer.exe").is_file() or bool(_shutil.which("LemonadeServer") or _shutil.which("lemonade-server"))

    def _run_stream(self,cmd):
        """명령을 실행하고 출력을 로그 큐로 스트리밍. 종료코드 반환."""
        flags=0x08000000 if os.name=="nt" else 0
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                           encoding="utf-8",errors="replace",creationflags=flags)
        for line in p.stdout:self.q.put(("LOG",line))
        return p.wait()

    def install_prerequisites(self):
        self.status.set("필수사항 확인/설치 중...")
        def work():
            try:
                # --- 1) Python 3.12 ---
                if self._python312_ok():
                    self._log("[필수] Python 3.12: 이미 설치됨 - 건너뜀")
                else:
                    self._log("[필수] Python 3.12 미설치 -> winget으로 설치 시도")
                    if _shutil.which("winget"):
                        code=self._run_stream(["winget","install","-e","--id","Python.Python.3.12",
                                               "--accept-source-agreements","--accept-package-agreements",
                                               "--silent"])
                        if code==0 and self._python312_ok():
                            self._log("[필수] Python 3.12 설치 완료")
                        else:
                            self._log(f"[필수][경고] winget 설치가 완료되지 않음 (코드 {code}). "
                                      "python.org 다운로드 페이지를 엽니다 - 수동 설치 후 다시 눌러주세요.")
                            webbrowser.open("https://www.python.org/downloads/release/python-3129/")
                            self.after(0,lambda:self.status.set("Python 수동 설치 필요"))
                            return
                    else:
                        self._log("[필수][경고] winget이 없어 자동 설치 불가. "
                                  "python.org 다운로드 페이지를 엽니다 - 'Add to PATH' 체크 후 설치하세요.")
                        webbrowser.open("https://www.python.org/downloads/release/python-3129/")
                        self.after(0,lambda:self.status.set("Python 수동 설치 필요"))
                        return

                # --- 2) Lemonade Server (C++ 앱) ---
                if self._lemonade_ok():
                    self._log("[필수] Lemonade Server: 이미 설치됨 - 건너뜀")
                else:
                    self._log("[필수] Lemonade Server 미설치 -> GitHub 최신 릴리스 조회 중...")
                    try:
                        with urllib.request.urlopen(
                            "https://api.github.com/repos/lemonade-sdk/lemonade/releases/latest",
                            timeout=15) as r:
                            rel=json.load(r)
                        assets=rel.get("assets",[])
                        # Windows 인스톨러(.exe) 자산 선택 (이름에 win/setup/installer 우선)
                        cand=[a for a in assets if a.get("name","").lower().endswith(".exe")]
                        cand.sort(key=lambda a:sum(k in a.get("name","").lower()
                                                   for k in ("win","setup","installer","server")),reverse=True)
                        if not cand:
                            raise RuntimeError("릴리스에서 .exe 인스톨러를 찾지 못함")
                        url=cand[0]["browser_download_url"]; name=cand[0]["name"]
                        dst=Path(tempfile.gettempdir())/name
                        self._log(f"[필수] 다운로드: {name} ({cand[0].get('size',0)//1048576}MB)...")
                        urllib.request.urlretrieve(url,dst)
                        self._log("[필수] 인스톨러 실행 - 설치 창의 안내를 따라 설치를 완료하세요.")
                        subprocess.Popen([str(dst)])
                        self._log("[필수] Lemonade 설치가 끝나면 이 버튼을 다시 눌러 확인하세요.")
                    except Exception as e:
                        self._log(f"[필수][경고] 자동 다운로드 실패({e}). 릴리스 페이지를 엽니다.")
                        webbrowser.open("https://github.com/lemonade-sdk/lemonade/releases/latest")

                # --- 3) pip requirements ---
                req=APP_DIR/"requirements.txt"
                pyexe=next((p for p in _real_python_candidates() if "WindowsApps" not in p),None)
                if req.exists() and pyexe:
                    self._log(f"[필수] pip 요구사항 설치 ({pyexe})...")
                    code=self._run_stream([pyexe,"-m","pip","install","--upgrade","-r",str(req)])
                    self._log("[필수] pip 요구사항 "+("설치 완료" if code==0 else f"설치 실패 (코드 {code})"))
                self.after(0,lambda:self.status.set("필수사항 확인/설치 완료 - 로그 확인"))
            except Exception:
                self.q.put(("LOG",traceback.format_exc()))
                self.after(0,lambda:self.status.set("필수사항 설치 중 오류"))
        threading.Thread(target=work,daemon=True).start()

    # ------------------------------------------------------------------
    # 설정(API 키 등) 저장/복원 - 앱 재시작해도 이어서 사용 가능하게
    # 주의: 키는 base64로 살짝 가려둘 뿐 암호화가 아니다(로컬 개인 PC 사용 전제).
    # ------------------------------------------------------------------
    def save_config(self):
        try:
            data={
                "api_rows":[{"provider":pv.get(),"on":on.get(),
                            "key":base64.b64encode(key.get().encode("utf-8")).decode("ascii")}
                           for _,on,pv,key in self.api_rows],
                "src":self.src.get(),"dst":self.dst.get(),
                "model":self.model.get(),"use_npu":self.use_npu.get(),
                "chars":self.chars.get(),"segs":self.segs.get(),"tokens":self.tokens.get(),
            }
            CONFIG_DIR.mkdir(parents=True,exist_ok=True)
            CONFIG_PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        except Exception as e:
            print(f"[설정 저장 실패] {e}",file=sys.stderr)

    def load_config(self) -> bool:
        """저장된 설정이 있으면 복원. 복원했으면 True (기본 API 행 3개를 추가하지 않도록)."""
        if not CONFIG_PATH.exists():
            return False
        try:
            data=json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[설정 로드 실패] {e}",file=sys.stderr)
            return False
        rows=data.get("api_rows") or []
        for r in rows:
            self.add_api(r.get("provider","gemini"))
            item=self.api_rows[-1]
            item[1].set(bool(r.get("on",False)))
            try:
                item[3].set(base64.b64decode(r.get("key","").encode("ascii")).decode("utf-8"))
            except Exception:
                pass
        if data.get("src"):self.src.set(data["src"])
        if data.get("dst"):self.dst.set(data["dst"])
        if data.get("model"):self.model.set(data["model"])
        if "use_npu" in data:self.use_npu.set(data["use_npu"])
        if data.get("chars"):self.chars.set(data["chars"])
        if data.get("segs"):self.segs.set(data["segs"])
        if data.get("tokens"):self.tokens.set(data["tokens"])
        return bool(rows)

    def on_close(self):
        self.save_config()
        self.destroy()

    def install_requirements(self):
        req=APP_DIR/"requirements.txt"
        if not req.exists():
            return messagebox.showerror("오류",f"requirements.txt를 찾을 수 없습니다.\n{req}")
        candidates=_real_python_candidates()
        pyexe=next((p for p in candidates if "WindowsApps" not in p),None)
        if not pyexe:
            return messagebox.showerror("오류","실제 Python 실행 파일을 찾지 못했습니다.")
        self.status.set("요구사항 설치 중...")
        self.log.insert("end",f"[설치] Python: {pyexe}\n[설치] requirements: {req}\n")
        def work():
            try:
                flags=0x08000000 if os.name=="nt" else 0
                proc=subprocess.Popen([pyexe,"-m","pip","install","--upgrade","-r",str(req)],
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                    encoding="utf-8",errors="replace",creationflags=flags)
                for line in proc.stdout:self.q.put(("LOG",line))
                code=proc.wait()
                self.after(0,lambda:self.status.set("요구사항 설치 완료" if code==0 else f"설치 실패 ({code})"))
                self.after(0,lambda:messagebox.showinfo("설치 결과","요구사항 설치가 완료되었습니다. GUI를 다시 실행하세요.") if code==0 else messagebox.showerror("설치 실패",f"종료 코드: {code}"))
            except Exception as e:
                self.after(0,lambda:messagebox.showerror("설치 오류",str(e)))
        threading.Thread(target=work,daemon=True).start()

    def pick(self,var,save):
        p=filedialog.asksaveasfilename(defaultextension=".pdf",filetypes=[("PDF","*.pdf")]) if save else filedialog.askopenfilename(filetypes=[("PDF","*.pdf")])
        if p:var.set(p)

    def refresh_models(self):
        self.status.set("Lemonade 모델 조회 중...")
        def work():
            found=[]
            try:
                with urllib.request.urlopen(f"http://localhost:{PORT}/api/v1/models",timeout=3) as r:d=json.load(r)
                items=d.get("data",[]) if isinstance(d,dict) else d
                for x in items:
                    m=(x.get("id") or x.get("model") or x.get("name")) if isinstance(x,dict) else str(x)
                    if m and m not in found:found.append(m)
            except Exception:pass
            self.after(0,lambda:self.set_models(found))
        threading.Thread(target=work,daemon=True).start()

    def set_models(self,found):
        if not found:found=["gemma4-it-e2b-FLM","gemma4-it-e4b-FLM","qwen3-it-4b-FLM"]
        self.models["values"]=found
        if self.model.get() not in found:self.model.set(found[0])
        self.model_changed(); self.status.set("대기 중" if found else "Lemonade 서버 연결 실패")

    def model_changed(self,*_):
        c,s,t=preset(self.model.get()); self.chars.set(str(c)); self.segs.set(str(s)); self.tokens.set(str(t))

    def start(self):
        if not self.inp.get():
            return messagebox.showerror("오류","입력 PDF를 선택하세요.")
        try:
            int(self.chars.get()); int(self.segs.get()); int(self.tokens.get())
        except ValueError:
            return messagebox.showerror("오류","배치/세그먼트/max_tokens는 숫자여야 합니다.")

        self.save_config()  # 입력한 API 키/설정을 즉시 저장 (다음 실행 시 이어서 사용)

        keys=[]
        for _,on,pv,key in self.api_rows:
            if on.get() and key.get().strip():
                keys.append(f"{pv.get()}:{key.get().strip()}")
        if not keys and not self.use_npu.get():
            return messagebox.showerror("오류","사용할 API 또는 로컬 NPU를 선택하세요.")

        fd,self.keyfile=tempfile.mkstemp(prefix="pdftranslator_",suffix=".txt")
        os.close(fd)
        Path(self.keyfile).write_text("\n".join(keys),encoding="utf-8")

        argv=[str(ENGINE),self.inp.get(),
              "--source-lang",self.src.get(),"--target-lang",self.dst.get(),
              "--batch-chars",self.chars.get(),"--batch-segs",self.segs.get(),
              "--max-tokens",self.tokens.get(),"--api-key-file",self.keyfile,
              "--model-local",self.model.get(),"--model-select-timeout","0"]
        if self.pages.get().strip(): argv+=["--pages",self.pages.get().strip()]
        if self.out.get().strip(): argv+=["-o",self.out.get().strip()]
        if self.use_npu.get(): argv+=["--local-npu"]

        self.log.delete("1.0","end")
        self.engine_completed=False
        self.progress["value"]=0
        self.pct=0.0
        self.start_time=time.time()
        self.prog_info.set(f"시작: {time.strftime('%H:%M:%S')}")
        self.startbtn["state"]="disabled"
        self.stopbtn["state"]="normal"
        self.status.set("번역 시작")

        class QueueWriter(io.TextIOBase):
            def __init__(self,q): self.q=q
            def write(self,s):
                if s: self.q.put(("LOG",s))
                return len(s)
            def flush(self): pass

        def run():
            old_argv=sys.argv[:]
            old_env={k:os.environ.get(k) for k in ("PYTHONIOENCODING","PYTHONUTF8")}
            try:
                sys.argv=argv
                # EXE에서는 translate_pdf.py를 외부 프로세스로 재실행하지 않고
                # 동일 프로세스에 번들된 모듈로 import하여 main()을 호출한다.
                engine=importlib.import_module("translate_pdf")
                self.engine=engine
                if hasattr(engine,"reset_stop"): engine.reset_stop()
                writer=QueueWriter(self.q)
                with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                    try:
                        engine.main()
                        code=0
                    except SystemExit as e:
                        code=e.code if isinstance(e.code,int) else (0 if e.code is None else 1)
                        if e.code and not isinstance(e.code,int):
                            print(e.code)
                self.q.put(("DONE",code))
            except Exception:
                self.q.put(("LOG",traceback.format_exc()))
                self.q.put(("ERR","번역 엔진 실행 중 예외가 발생했습니다. 로그를 확인하세요."))
            finally:
                sys.argv=old_argv
                for k,v in old_env.items():
                    if v is None: os.environ.pop(k,None)
                    else: os.environ[k]=v
        threading.Thread(target=run,daemon=True).start()

    def poll(self):
        try:
            while True:
                typ,val=self.q.get_nowait()
                if typ=="LOG":
                    self.log.insert("end",val);self.log.see("end")
                    # 엔진의 구조화 진행 라인: [진행] batch=i/N pages=p/P pct=xx.x
                    pm=re.search(r"\[진행\] batch=(\d+)/(\d+) pages=(\d+)/(\d+) pct=([\d.]+)",val)
                    if pm:
                        bi,bn,pd,pt,pct=int(pm.group(1)),int(pm.group(2)),int(pm.group(3)),int(pm.group(4)),float(pm.group(5))
                        self.pct=pct
                        self.progress["value"]=pct
                        self.status.set(f"번역 중 - 전체 {pt}페이지 중 {pd}페이지 진행 (배치 {bi}/{bn}, {pct:.1f}%)")
                    else:
                        m=re.search(r"\[batch (\d+)/(\d+)\]",val)
                        if m and self.pct==0:
                            self.progress["value"]=10+80*int(m.group(1))/max(1,int(m.group(2)))
                        elif "[1/4]" in val:self.progress["value"]=5
                        elif "[3/4]" in val:self.progress["value"]=max(self.progress["value"],92)
                        elif "[4/4]" in val:
                            self.progress["value"]=100
                            self.engine_completed=True
                else:
                    self.cleanup();self.startbtn["state"]="normal";self.stopbtn["state"]="disabled"
                    self.start_time=None
                    if typ=="DONE":
                        # 출력 PDF 재구성 완료 로그가 확인되면 후처리의 비핵심 종료코드보다 실제 결과를 우선한다.
                        effective_code = 0 if self.engine_completed else val
                        self.status.set("완료" if effective_code==0 else f"오류 종료 ({effective_code})")
                        if effective_code==0:self.progress["value"]=100
                        messagebox.showinfo("실행 종료","번역 및 PDF 저장이 완료되었습니다." if effective_code==0 else f"프로세스 종료 코드: {effective_code}")
                    else:self.status.set("오류");messagebox.showerror("오류",val)
        except queue.Empty:pass
        # 경과/예상 시간 갱신 (1초 단위 체감)
        if self.start_time:
            el=time.time()-self.start_time
            h,rem=divmod(int(el),3600); m,s=divmod(rem,60)
            eta="계산 중" if self.pct<=0 else time.strftime("%H:%M:%S",time.gmtime(el/self.pct*(100-self.pct)))
            self.prog_info.set(
                f"시작: {time.strftime('%H:%M:%S',time.localtime(self.start_time))}"
                f" | 경과: {h:02d}:{m:02d}:{s:02d}"
                f" | 예상 남은시간: {eta}"
                f" | 진행률: {self.pct:.1f}%")
        self.after(100,self.poll)

    def cleanup(self):
        if self.keyfile:
            try:os.remove(self.keyfile)
            except:pass
            self.keyfile=None
    def stop(self):
        """우아한 중단: 엔진에 중단 신호 -> 현재 배치까지 번역 후 나머지는 원문 유지 저장.
        저장된 파일명의 _untranslated 구간으로 나중에 이어서-번역 가능."""
        eng=self.engine
        if eng is None:
            eng=sys.modules.get("translate_pdf")
        if eng is not None and hasattr(eng,"request_stop"):
            eng.request_stop()
            self.stopbtn["state"]="disabled"
            self.status.set("중단 요청됨 - 현재 배치 완료 후 진행분까지 저장합니다...")
            self.log.insert("end","[GUI] 중단 요청 - 현재 처리 중인 배치가 끝나면 "
                                  "번역된 부분까지 PDF로 저장됩니다.\n")
            self.log.see("end")
        else:
            messagebox.showinfo("중지 안내","실행 중인 번역 작업이 없습니다.")

if __name__=="__main__":
    App().mainloop()
