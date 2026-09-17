# -*- coding: utf-8 -*-
"""한컴오피스 실렌더 검증 (validate_hwpx 의 L5).

이 PC에 한글 13.0(Office 2024)이 설치돼 있어 "실제로 열리는가"를 자동화할 수 있다.
  C:\\Program Files (x86)\\Hnc\\Office 2024\\HOffice130\\Bin\\Hwp.exe

확인하는 것:
  1. 파일이 열리는가 (깨진 XML/참조는 여기서 걸린다)
  2. 페이지 수 (분량 제한 준수)
  3. 텍스트 추출 결과 (LLM Council 채점기가 읽을 내용)
  4. PDF 변환 (레이아웃 육안 검증용)

사용:
    PYTHONPATH=$CLAUDE_PLUGIN_ROOT python -m engine.hwpx.hancom_check <파일.hwpx> [--pdf out.pdf] [--json report.json]
exit: 0 정상 / 2 열기 실패
"""
import argparse
import json
import os
import sys

HWP_EXE = r"C:\Program Files (x86)\Hnc\Office 2024\HOffice130\Bin\Hwp.exe"


_PS_KILL_HEADLESS = r"""
$titled = @()
foreach ($p in (Get-Process Hwp -ErrorAction SilentlyContinue)) {
  if ([string]::IsNullOrEmpty($p.MainWindowTitle)) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  } else { $titled += $p.MainWindowTitle }
}
if ($titled.Count -gt 0) { Write-Output ("TITLED_HWP=" + ($titled -join "|")) }
"""


def kill_stale():
    """멈춘 Hwp.exe 정리.

    ★ 결함 정정(2026-08-26): 전에는 `taskkill /F /IM Hwp.exe` 로 **전부** 죽였다.
      사용자가 열어 놓고 저장하지 않은 문서까지 강제 종료된다 — 자료 유실 위험이다.

      류박사님 하네스의 `gate_pages.py` 가 더 안전한 방법을 쓴다:
      **창 제목이 없는(=사용자 문서가 아닌) 잔류 인스턴스만** 정리하고,
      창이 있는 인스턴스는 절대 건드리지 않는다. 그쪽을 따른다.

      돌려주는 값: 사용자가 열어 둔 문서 제목 목록(있으면 쪽수가 흔들릴 수 있다).
    """
    import subprocess
    import time
    titled = []
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                            _PS_KILL_HEADLESS],
                           capture_output=True, text=True, errors="replace",
                           timeout=30)
        for line in (r.stdout or "").splitlines():
            if line.startswith("TITLED_HWP="):
                titled = [t for t in line[len("TITLED_HWP="):].split("|") if t]
        time.sleep(0.5)
    except Exception:                                       # noqa: BLE001
        pass
    return titled


_PS_MEASURE = r"""
param([string]$src, [string]$dst)
$ErrorActionPreference = "Stop"
foreach ($p in (Get-Process Hwp -ErrorAction SilentlyContinue)) {
  if ([string]::IsNullOrEmpty($p.MainWindowTitle)) {
    Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
  }
}
Start-Sleep -Milliseconds 300
$hwp = New-Object -ComObject HWPFrame.HwpObject
try { $null = $hwp.RegisterModule("FilePathCheckDLL","FilePathCheckerModule") } catch { }
$null = $hwp.Open($src, "", "forceopen:true")
$null = $hwp.HAction.Run("MoveDocEnd")
Write-Output ("PAGECOUNT=" + $hwp.PageCount)
if ($dst) { $null = $hwp.SaveAs($dst, "PDF", ""); Write-Output ("SAVED=" + (Test-Path -LiteralPath $dst)) }
$hwp.Quit()
"""


def check_via_powershell(path, pdf_out=None, timeout=180):
    """★ 폴백 — PowerShell 로 한컴 COM 을 부른다.

    이 PC 실측(2026-08-26): `win32com.gencache.EnsureDispatch` 경로가
    `-2147023170 원격 프로시저를 호출하지 못했습니다` 로 계속 죽는데,
    **같은 순간 PowerShell 의 `New-Object -ComObject` 는 정상 동작했다.**
    (류박사님 하네스 `gate_pages.py` 가 쓰는 방식이다.)

    차이가 셋이다 — ⑴ gencache 캐시를 타지 않는 늦은 바인딩,
    ⑵ 보안모듈 두 번째 인자가 `FilePathCheckerModule`(우리는 `FilePathChecker`),
    ⑶ 잔류 인스턴스를 전부 죽이지 않고 창 없는 것만 정리.

    어느 것이 결정적인지는 분리하지 못했다. 폴백으로 둔다.
    """
    import re
    import subprocess
    import tempfile

    path = os.path.abspath(path)
    rep = {"file": path, "opened": False, "pages": None, "text_chars": 0,
           "text_head": "", "pdf": None, "errors": [], "via": "powershell"}
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False,
                                     encoding="utf-8-sig") as f:
        # ★ BOM 필수 — PowerShell 5.1 은 BOM 없는 .ps1 을 cp949 로 읽어
        #   한글 주석이 깨지면 그 뒤 줄이 통째로 먹힌다(원 저작자 실측).
        f.write(_PS_MEASURE)
        ps = f.name
    args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", ps, "-src", path]
    if pdf_out:
        pdf_out = os.path.abspath(pdf_out)
        os.makedirs(os.path.dirname(pdf_out) or ".", exist_ok=True)
        args += ["-dst", pdf_out]
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
    except Exception as e:                                  # noqa: BLE001
        rep["errors"].append(f"PowerShell 폴백 실패: {e}")
        return rep
    finally:
        try:
            os.unlink(ps)
        except OSError:
            pass
    m = re.search(r"PAGECOUNT=(\d+)", r.stdout or "")
    if not m:
        rep["errors"].append(
            "PowerShell COM 실패: " + ((r.stdout or "") + (r.stderr or ""))[:200])
        return rep
    rep["opened"] = True
    rep["pages"] = int(m.group(1))
    if pdf_out and os.path.exists(pdf_out):
        rep["pdf"] = pdf_out
    return rep


def _register_security_module(hwp):
    """파일 접근 보안 대화상자를 억제한다.

    등록돼 있지 않으면 한글이 '다른 프로그램이 문서를 열려고 합니다' 모달을 띄우고
    스크립트가 그대로 멈춘다. 등록 실패해도 치명적이지 않으므로 경고만 낸다.
    """
    try:
        hwp.RegisterModule("FilePathCheckDLL", "FilePathChecker")
        return True
    except Exception as e:                                  # noqa: BLE001
        print(f"  [warn] 보안모듈 등록 실패: {e}", file=sys.stderr)
        return False


def check(path, pdf_out=None, visible=False):
    """HWPX를 한글로 열어 검증한다. dict 리포트를 돌려준다."""
    import win32com.client as win32

    path = os.path.abspath(path)
    report = {"file": path, "opened": False, "pages": None,
              "text_chars": 0, "text_head": "", "pdf": None, "errors": []}

    # ★ 디스패치 전에 잔류 프로세스를 정리한다.
    #   앞선 실행이 남긴 Hwp.exe에 붙으면 Open()이 대화상자를 띄우며 무한
    #   대기한다(실측: 프로세스 2개가 남아 검증이 5분 타임아웃).
    #   DispatchEx로 새 인스턴스를 강제하는 방법은 오히려 더 자주 멈췄다.
    titled = kill_stale()
    if titled:
        report["errors"].append(
            "주의: 한글 창이 열려 있다(" + "|".join(titled)[:60] +
            ") — 열린 인스턴스에 붙으면 쪽수가 흔들릴 수 있다")
    try:
        hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    except Exception as e:                                  # noqa: BLE001
        # ★ 이 PC 실측: gencache 경로가 RPC 오류로 죽는다. PowerShell 로 넘긴다.
        report["errors"].append(f"pywin32 디스패치 실패 → PowerShell 폴백: {e}")
        fb = check_via_powershell(path, pdf_out)
        fb["errors"] = report["errors"] + fb["errors"]
        return fb
    try:
        _register_security_module(hwp)
        try:
            hwp.XHwpWindows.Item(0).Visible = bool(visible)
        except Exception:                                   # noqa: BLE001
            pass

        # format="HWPX" 를 명시하지 않으면 확장자로 추론한다.
        if not hwp.Open(path, "HWPX", "forceopen:true"):
            report["errors"].append("Open() 이 False 를 반환했다 (파일 손상 의심)")
            return report
        report["opened"] = True

        # 페이지 수
        try:
            report["pages"] = hwp.PageCount
        except Exception as e:                              # noqa: BLE001
            report["errors"].append(f"PageCount 실패: {e}")

        # 텍스트 추출 — LLM Council 채점기가 보게 될 내용의 근사치
        try:
            hwp.InitScan(option=0x07)
            buf = []
            while True:
                state, text = hwp.GetText()
                if state in (0, 1):
                    break
                buf.append(text)
            hwp.ReleaseScan()
            full = "".join(buf)
            report["text_chars"] = len(full)
            report["text_head"] = full[:400]
        except Exception as e:                              # noqa: BLE001
            report["errors"].append(f"텍스트 추출 실패: {e}")

        if pdf_out:
            pdf_out = os.path.abspath(pdf_out)
            os.makedirs(os.path.dirname(pdf_out), exist_ok=True)
            try:
                hwp.SaveAs(pdf_out, "PDF", "")
                report["pdf"] = pdf_out if os.path.exists(pdf_out) else None
                if not report["pdf"]:
                    report["errors"].append("SaveAs(PDF) 후 파일이 없다")
            except Exception as e:                          # noqa: BLE001
                report["errors"].append(f"PDF 변환 실패: {e}")
    finally:
        try:
            hwp.Clear(option=1)          # 저장 안 함
            hwp.Quit()
        except Exception:                                   # noqa: BLE001
            pass
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--pdf")
    ap.add_argument("--json")
    ap.add_argument("--visible", action="store_true", help="한글 창을 띄운다")
    a = ap.parse_args()

    if not os.path.exists(HWP_EXE):
        print(f"[skip] 한글이 없다: {HWP_EXE}", file=sys.stderr)
        return 0                                   # 없는 환경에서는 건너뛴다

    r = check(a.file, a.pdf, a.visible)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)

    print(f"opened     : {r['opened']}")
    print(f"pages      : {r['pages']}")
    print(f"text_chars : {r['text_chars']}")
    if r["text_head"]:
        print(f"text_head  : {r['text_head'][:120]!r}")
    if r["pdf"]:
        print(f"pdf        : {r['pdf']}")
    for e in r["errors"]:
        print(f"[error] {e}", file=sys.stderr)
    return 0 if r["opened"] else 2


if __name__ == "__main__":
    sys.exit(main())
