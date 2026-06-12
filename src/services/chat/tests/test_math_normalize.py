"""Tests for the math-normalizer at the SSE seam.

TDD: written before _normalize_math exists so the import fails (red).
After api.py is patched the tests go green.

Behaviour contract:
- ONLY inside $...$ and $$...$$ spans, prefix bare Greek/operator tokens
  with a backslash when they are NOT already preceded by one and NOT part
  of a longer alnum identifier.
- Tokens already escaped (e.g. \\delta) are left alone.
- Prose OUTSIDE math spans is NEVER modified.
- Recursively handles str / dict / list like _strip_ctrl.
"""
from __future__ import annotations

import importlib
import sys

import pytest


# ---------------------------------------------------------------------------
# Import helper under test
# ---------------------------------------------------------------------------


def _import_normalize_math():
    """Import _normalize_math from api.py, reloading to pick up edits."""
    mod_name = "src.services.chat.api"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    return mod._normalize_math  # noqa: SLF001


# ---------------------------------------------------------------------------
# Unit tests: _normalize_math
# ---------------------------------------------------------------------------


class TestNormalizeMath:
    def setup_method(self):
        self.norm = _import_normalize_math()

    # --- bare Greek inside inline math ---

    def test_bare_phi_fixed(self):
        """$Phi$ → $\\Phi$ (capital Phi was rendered as literal 'Phi')."""
        assert self.norm("$Phi$") == r"$\Phi$"

    def test_bare_delta_fixed(self):
        """$delta$ → $\\delta$."""
        assert self.norm("$delta$") == r"$\delta$"

    def test_bare_mu_fixed(self):
        """$mu$ → $\\mu$."""
        assert self.norm("$mu$") == r"$\mu$"

    def test_bare_sigma_fixed(self):
        """$sigma^2$ → $\\sigma^2$."""
        assert self.norm("$sigma^2$") == r"$\sigma^2$"

    # --- bare operator inside inline math ---

    def test_bare_to_fixed(self):
        """$sigma^2 to 0$ → $\\sigma^2 \\to 0$."""
        result = self.norm("$sigma^2 to 0$")
        assert result == r"$\sigma^2 \to 0$"

    def test_mixed_bare_math(self):
        """DB ground-truth: $\\mathbb{P}[|X-mu|>delta]$ — mu+delta fixed,
        \\mathbb already escaped (not in allowlist anyway)."""
        inp = r"$\mathbb{P}[|X-mu|>delta]$"
        out = self.norm(inp)
        assert out == r"$\mathbb{P}[|X-\mu|>\delta]$"

    # --- already-escaped tokens must NOT be double-escaped ---

    def test_already_escaped_delta_unchanged(self):
        """$\\delta$ stays $\\delta$."""
        assert self.norm(r"$\delta$") == r"$\delta$"

    def test_already_escaped_mu_unchanged(self):
        """$\\mu$ stays $\\mu$."""
        assert self.norm(r"$\mu$") == r"$\mu$"

    def test_already_escaped_to_unchanged(self):
        """$$\\bar X_n \\to \\mu$$ stays unchanged."""
        s = r"$$\bar X_n \to \mu$$"
        assert self.norm(s) == s

    # --- longest-first: subseteq before subset ---

    def test_longest_first_subseteq(self):
        """$subseteq$ → $\\subseteq$ (NOT $\\subset eq$)."""
        assert self.norm("$subseteq$") == r"$\subseteq$"

    def test_longest_first_varepsilon(self):
        """$varepsilon$ → $\\varepsilon$ (NOT $var\\epsilon$)."""
        assert self.norm("$varepsilon$") == r"$\varepsilon$"

    # --- tokens in prose outside math MUST NOT be touched ---

    def test_prose_to_unchanged(self):
        """'we go to the limit' — 'to' outside math stays literal."""
        s = "we go to the limit"
        assert self.norm(s) == s

    def test_prose_in_unchanged(self):
        """'contained in the set' — 'in' outside math stays literal."""
        s = "contained in the set"
        assert self.norm(s) == s

    def test_prose_pi_unchanged(self):
        """Prose word 'pi' not inside math — unchanged."""
        s = "the constant pi is approximately 3.14"
        assert self.norm(s) == s

    # --- pi in longer identifier must NOT be touched ---

    def test_pi_in_pixel_unchanged(self):
        """$pixel$ — 'pi' is followed by 'x', so must NOT be prefixed."""
        assert self.norm("$pixel$") == "$pixel$"

    def test_pi_standalone_fixed(self):
        """$pi$ → $\\pi$ (standalone 'pi')."""
        assert self.norm("$pi$") == r"$\pi$"

    # --- non-allowlist commands must NOT be touched ---

    def test_mathbb_unchanged(self):
        """$\\mathbb{P}$ — \\mathbb not in allowlist, already escaped; unchanged."""
        s = r"$\mathbb{P}$"
        assert self.norm(s) == s

    def test_frac_unchanged(self):
        """$\\frac{1}{n}$ — unchanged."""
        s = r"$\frac{1}{n}$"
        assert self.norm(s) == s

    def test_overline_unchanged(self):
        """$\\overline{X}_n$ — unchanged."""
        s = r"$\overline{X}_n$"
        assert self.norm(s) == s

    def test_mathrm_unchanged(self):
        """$\\mathrm{Var}(X)$ — unchanged."""
        s = r"$\mathrm{Var}(X)$"
        assert self.norm(s) == s

    # --- display math $$...$$ ---

    def test_display_math_bare_tokens_fixed(self):
        """$$sigma^2 + mu$$ → $$\\sigma^2 + \\mu$$."""
        assert self.norm("$$sigma^2 + mu$$") == r"$$\sigma^2 + \mu$$"

    def test_display_math_already_escaped_unchanged(self):
        """$$\\bar X_n \\to \\mu$$ — all already escaped; unchanged."""
        s = r"$$\bar X_n \to \mu$$"
        assert self.norm(s) == s

    # --- x_{mu} subscript case (documented acceptable behaviour) ---

    def test_subscript_bare_mu_fixed(self):
        """$x_{mu}$ → $x_{\\mu}$ — more correct; documented as acceptable."""
        assert self.norm("$x_{mu}$") == r"$x_{\mu}$"

    # --- no-op when no $ present ---

    def test_no_dollar_passthrough(self):
        """String with no $ is returned untouched (fast path)."""
        s = "plain prose with delta and sigma and mu"
        assert self.norm(s) == s

    # --- recursion over dict and list ---

    def test_dict_recursion(self):
        """Bare tokens in nested dict values are normalised."""
        inp = {"aspects": {"tldr": "$delta$", "body": "no math here"}}
        out = self.norm(inp)
        assert out == {"aspects": {"tldr": r"$\delta$", "body": "no math here"}}

    def test_list_recursion(self):
        """Bare tokens in list entries are normalised."""
        inp = ["$mu$", "$sigma^2$", "plain text"]
        out = self.norm(inp)
        assert out == [r"$\mu$", r"$\sigma^2$", "plain text"]

    def test_non_string_passthrough(self):
        """Numbers, None, booleans pass through unchanged."""
        assert self.norm(42) == 42
        assert self.norm(None) is None
        assert self.norm(True) is True

    # --- combined inline + surrounding prose ---

    def test_mixed_prose_and_math(self):
        """Prose outside $ untouched; bare tokens inside $ fixed."""
        s = "the tail shaped by the function $Phi$, as $delta$ grows"
        out = self.norm(s)
        assert out == r"the tail shaped by the function $\Phi$, as $\delta$ grows"

    # --- full DB ground-truth sentence ---

    def test_db_ground_truth_sentence(self):
        """Exact DB content: multiple bare tokens in one sentence."""
        s = "tail shaped by the function $Phi$, ... as $delta$ grows"
        out = self.norm(s)
        assert r"$\Phi$" in out
        assert r"$\delta$" in out
        # prose 'as' between math spans is untouched
        assert "as" in out

    # --- Fix 1: accent / structure commands ---

    def test_bare_hat_fixed(self):
        """$hat{\\mu}=\\overline{X}_n$ — bare hat gets backslash; overline already escaped."""
        result = self.norm("$hat{\\mu}=\\overline{X}_n$")
        assert result == "$\\hat{\\mu}=\\overline{X}_n$"

    def test_already_escaped_widehat_unchanged(self):
        """$\\widehat{\\theta}$ — already escaped; must not be double-escaped."""
        s = "$\\widehat{\\theta}$"
        assert self.norm(s) == s

    def test_bare_widehat_fixed(self):
        """$widehat{\\theta}$ — bare widehat gets backslash."""
        assert self.norm("$widehat{\\theta}$") == "$\\widehat{\\theta}$"

    def test_hat_in_somehat_unchanged(self):
        """$somehat$ — 'hat' is preceded by letters; must NOT be matched."""
        assert self.norm("$somehat$") == "$somehat$"

    def test_bare_tilde_fixed(self):
        """$tilde{x}$ → $\\tilde{x}$."""
        assert self.norm("$tilde{x}$") == "$\\tilde{x}$"

    def test_already_escaped_tilde_unchanged(self):
        """$\\tilde{x}$ unchanged."""
        s = "$\\tilde{x}$"
        assert self.norm(s) == s

    def test_bare_bar_fixed(self):
        """$bar{X}$ → $\\bar{X}$."""
        assert self.norm("$bar{X}$") == "$\\bar{X}$"

    def test_bar_in_overbar_unchanged(self):
        """$overbar{X}$ — 'bar' preceded by 'over'; must NOT be matched."""
        assert self.norm("$overbar{X}$") == "$overbar{X}$"

    def test_bare_vec_fixed(self):
        """$vec{v}$ → $\\vec{v}$."""
        assert self.norm("$vec{v}$") == "$\\vec{v}$"

    def test_bare_overline_fixed(self):
        """$overline{X}$ → $\\overline{X}$ (bare overline)."""
        assert self.norm("$overline{X}$") == "$\\overline{X}$"

    def test_widehat_before_hat_ordering(self):
        """widehat must appear before hat in _GREEKOPS so $widehat{}$ is not
        matched as $wide\\hat{}$."""
        # If ordering is wrong, widehat would become wide\hat — test catches it
        result = self.norm("$widehat{x}$")
        assert result == "$\\widehat{x}$"
        assert "wide\\hat" not in result

    def test_widetilde_before_tilde_ordering(self):
        """$widetilde{x}$ → $\\widetilde{x}$ (not $wide\\tilde{x}$)."""
        result = self.norm("$widetilde{x}$")
        assert result == "$\\widetilde{x}$"
        assert "wide\\tilde" not in result

    def test_live_db_hat_mu_combined(self):
        """Live DB evidence: $hat{\\mu}=\\overline{X}_n$ full match."""
        inp = "$hat{\\mu}=\\overline{X}_n$"
        assert self.norm(inp) == "$\\hat{\\mu}=\\overline{X}_n$"

    def test_bare_ddot_fixed(self):
        """$ddot{x}$ → $\\ddot{x}$."""
        assert self.norm("$ddot{x}$") == "$\\ddot{x}$"

    def test_bare_dot_fixed(self):
        """$dot{x}$ → $\\dot{x}$ (standalone dot)."""
        assert self.norm("$dot{x}$") == "$\\dot{x}$"

    def test_dot_in_ddot_ordering(self):
        """ddot before dot: $ddot{x}$ must not become $d\\dot{x}$."""
        result = self.norm("$ddot{x}$")
        assert result == "$\\ddot{x}$"
        assert "d\\dot" not in result

    def test_bare_check_fixed(self):
        """$check{x}$ → $\\check{x}$."""
        assert self.norm("$check{x}$") == "$\\check{x}$"

    def test_bare_acute_fixed(self):
        """$acute{x}$ → $\\acute{x}$."""
        assert self.norm("$acute{x}$") == "$\\acute{x}$"

    def test_bare_grave_fixed(self):
        """$grave{x}$ → $\\grave{x}$."""
        assert self.norm("$grave{x}$") == "$\\grave{x}$"

    def test_bare_breve_fixed(self):
        """$breve{x}$ → $\\breve{x}$."""
        assert self.norm("$breve{x}$") == "$\\breve{x}$"

    def test_bare_underline_fixed(self):
        """$underline{x}$ → $\\underline{x}$."""
        assert self.norm("$underline{x}$") == "$\\underline{x}$"
