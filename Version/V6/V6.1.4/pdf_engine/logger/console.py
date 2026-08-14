import sys

from .base import Logger


class ConsoleLogger(Logger):
    def log(self, message: str, level: str = 'INFO') -> None:
        line = f'[{level}] {message}'
        try:
            print(line)
        except UnicodeEncodeError:
            # 한국어 Windows 콘솔은 기본 인코딩이 cp949라서, 로그에 섞여 나오는
            # 특수문자(보호 토큰 ⟦PH0⟧의 U+27E6 등)를 만나면 print 자체가 예외를 던진다.
            # 그러면 '로그를 찍다가' 번역 작업 전체가 죽어버린다(실제로 확인된 문제).
            # 인코딩할 수 없는 문자는 대체 문자로 바꿔서라도 반드시 출력만 하고 넘어간다.
            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            sys.stdout.write(line.encode(enc, "replace").decode(enc, "replace") + "\n")
