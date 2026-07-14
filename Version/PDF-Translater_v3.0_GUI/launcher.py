import sys
if len(sys.argv)>1:
 import runpy
 sys.argv[0]="translate_pdf.py"
 runpy.run_path("translate_pdf.py",run_name="__main__")
else:
 import gui
