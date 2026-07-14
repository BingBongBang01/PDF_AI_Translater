#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess, threading, queue, tempfile, os, sys, json, re, urllib.request
import contextlib, io, traceback, importlib, shutil as _shutil
from pathlib import Path

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ENGINE = APP_DIR / "translate_pdf.py"
PORT = 13305

def _real_python_candidates():
    found=[]
    if os.name=="nt":
        try:
            p=subprocess.check_output(["py","-3.12","-c","import sys;print(sys.executable)"],
                                      text=True,stderr=subprocess.DEVNULL).strip()
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
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15).returncode==0
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
        self.title("PDF Translater v3.7")
        self.geometry("1000x800")
        self.minsize(850,650)
        self.q=queue.Queue(); self.proc=None; self.keyfile=None; self.engine_completed=False
        self.inp=tk.StringVar(); self.out=tk.StringVar(); self.pages=tk.StringVar()
        self.src=tk.StringVar(value="English"); self.dst=tk.StringVar(value="Korean")
        self.model=tk.StringVar(value="gemma4-it-e2b-FLM")
        self.chars=tk.StringVar(); self.segs=tk.StringVar(); self.tokens=tk.StringVar()
        self.use_npu=tk.BooleanVar(value=True); self.api_rows=[]
        self.build(); self.add_api("gemini"); self.add_api("anthropic"); self.add_api("openai")
        self.refresh_models(); self.after(100,self.poll)

    def build(self):
        main=ttk.Frame(self,padding=10); main.pack(fill="both",expand=True)
        f=ttk.LabelFrame(main,text="PDF 파일"); f.pack(fill="x")
        for r,(label,var,save) in enumerate((("입력 PDF",self.inp,False),("출력 PDF (비우면 자동 이름)",self.out,True))):
            ttk.Label(f,text=label,width=23).grid(row=r,column=0,padx=5,pady=5,sticky="w")
            ttk.Entry(f,textvariable=var).grid(row=r,column=1,padx=5,pady=5,sticky="ew")
            ttk.Button(f,text="찾기",command=lambda v=var,s=save:self.pick(v,s)).grid(row=r,column=2,padx=5)
        f.columnconfigure(1,weight=1)

        o=ttk.LabelFrame(main,text="기본 설정"); o.pack(fill="x",pady=7)
        for i,(label,var) in enumerate((("페이지 범위",self.pages),("원문 언어",self.src),("번역 언어",self.dst))):
            ttk.Label(o,text=label).grid(row=0,column=i*2,padx=5,pady=6)
            ttk.Entry(o,textvariable=var,width=20).grid(row=0,column=i*2+1,padx=5)

        a=ttk.LabelFrame(main,text="API 키 — 체크된 API만 사용"); a.pack(fill="x")
        self.api_frame=ttk.Frame(a); self.api_frame.pack(fill="x")
        api_buttons=ttk.Frame(a); api_buttons.pack(fill="x",padx=5,pady=4)
        ttk.Button(api_buttons,text="+ API 추가",command=lambda:self.add_api("gemini")).pack(side="left")
        ttk.Button(api_buttons,text="요구사항 설치",command=self.install_requirements).pack(side="left",padx=6)

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
        self.progress=ttk.Progressbar(main,maximum=100); self.progress.pack(fill="x",pady=5)
        buttons=ttk.Frame(main); buttons.pack(fill="x")
        self.startbtn=ttk.Button(buttons,text="번역 시작",command=self.start); self.startbtn.pack(side="left")
        ttk.Button(buttons,text="중지",command=self.stop).pack(side="left",padx=5)
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
        self.startbtn["state"]="disabled"
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
                    m=re.search(r"\[batch (\d+)/(\d+)\]",val)
                    if m:self.progress["value"]=10+80*int(m.group(1))/max(1,int(m.group(2)));self.status.set(f"배치 {m.group(1)}/{m.group(2)}")
                    elif "[1/4]" in val:self.progress["value"]=10
                    elif "[3/4]" in val:self.progress["value"]=90
                    elif "[4/4]" in val:
                        self.progress["value"]=100
                        self.engine_completed=True
                else:
                    self.cleanup();self.startbtn["state"]="normal"
                    if typ=="DONE":
                        # 출력 PDF 재구성 완료 로그가 확인되면 후처리의 비핵심 종료코드보다 실제 결과를 우선한다.
                        effective_code = 0 if self.engine_completed else val
                        self.status.set("완료" if effective_code==0 else f"오류 종료 ({effective_code})")
                        if effective_code==0:self.progress["value"]=100
                        messagebox.showinfo("실행 종료","번역 및 PDF 저장이 완료되었습니다." if effective_code==0 else f"프로세스 종료 코드: {effective_code}")
                    else:self.status.set("오류");messagebox.showerror("오류",val)
        except queue.Empty:pass
        self.after(100,self.poll)

    def cleanup(self):
        if self.keyfile:
            try:os.remove(self.keyfile)
            except:pass
            self.keyfile=None
    def stop(self):
        messagebox.showinfo("중지 안내","v3.1은 번역 엔진을 EXE 내부에서 실행합니다. 안전한 강제 중지는 지원하지 않습니다. 현재 배치가 끝날 때까지 기다려 주세요.")

if __name__=="__main__":
    App().mainloop()
