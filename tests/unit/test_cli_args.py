import subprocess
import sys


def run_cmd(args):
    # Run a CLI command and return (code, stdout, stderr)
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    return proc.returncode, out, err


def test_cli_version_flag_screen():
    code, out, err = run_cmd([sys.executable, "-m", "stockcharts.cli", "--version"])
    assert code == 0
    assert "stockcharts " in out


def test_cli_version_flag_rsi():
    code, out, err = run_cmd(["stockcharts-rsi-divergence", "--version"])
    assert code == 0
    assert "stockcharts " in out


def test_cli_invalid_flag():
    code, out, err = run_cmd(["stockcharts-rsi-divergence", "--not-a-flag"])
    assert code != 0
    assert "usage" in err.lower() or "error" in err.lower()


def test_cli_missing_input_filter_file(tmp_path):
    missing = tmp_path / "nope.csv"
    code, out, err = run_cmd(["stockcharts-screen", "--input-filter", str(missing), "--version"])
    # Should not crash; version exits early ignoring other args
    assert code == 0
