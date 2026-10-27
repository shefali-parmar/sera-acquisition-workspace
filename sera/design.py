"""Shared buyer-facing presentation; no data, storage, or model behavior."""

BACKGROUND = "#F7F9F8"
SOFT_BACKGROUND = "#EAF0ED"
TEXT = "#223A36"
MUTED_TEXT = "#49635C"
TEAL_TEXT = "#1B6258"

COMPARISON_CSS = """
.sera-comparison-wrap{overflow-x:auto;overflow-y:auto;max-height:34rem;border:1px solid #D5E2DD;border-radius:12px;background:#F7F9F8;margin:.75rem 0 1rem;isolation:isolate}
.sera-comparison-wrap:focus-visible{outline:2px solid #1B6258;outline-offset:3px}
.sera-comparison{width:100%;table-layout:fixed;border-collapse:separate;border-spacing:0;color:#223A36;font-family:inherit}
.sera-comparison caption{caption-side:bottom;text-align:left;padding:12px 14px;font-size:.875rem;line-height:1.45;color:#49635C}
.sera-comparison th,.sera-comparison td{padding:11px 13px;text-align:left;vertical-align:top;border-bottom:1px solid #D5E2DD;white-space:normal;overflow-wrap:anywhere;line-height:1.4;font-size:.875rem}
.sera-comparison thead th{position:sticky;top:0;z-index:3;background:#EAF0ED;font-weight:650;color:#223A36}
.sera-comparison thead th:first-child{left:0;width:150px;z-index:4}
.sera-comparison tbody th{position:sticky;left:0;z-index:2;background:#F0F5F2;font-weight:600}
.sera-comparison-value{display:block;font-weight:600;font-variant-numeric:tabular-nums}
.sera-comparison small{display:block;margin-top:5px;font-weight:400;font-size:.875rem;line-height:1.4;color:#49635C}
.sera-comparison-scrollhint{display:none;color:#49635C;font-size:.875rem;margin:.5rem 0 0}
@media(max-width:700px){.sera-comparison-scrollhint{display:block}.sera-comparison th,.sera-comparison td{padding:10px 11px}.sera-comparison thead th:first-child{width:132px}}
"""

_APP_RULES = """
.st-key-ma_scope{padding:.15rem 0;margin-bottom:.15rem}
.st-key-ma_scope p{margin-bottom:.2rem}
.st-key-ma_tasks [data-testid="stHorizontalBlock"]{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr));gap:.5rem}
.st-key-ma_tasks [data-testid="stColumn"]{width:100%!important;min-width:0!important}
.st-key-ma_tasks button{min-height:2.6rem;padding:.4rem .6rem;border-radius:999px!important;background:transparent}
.st-key-ma_tasks button [data-testid="stMarkdownContainer"]{white-space:normal!important;overflow:visible!important;text-overflow:clip!important}
.st-key-ma_tasks button p{font-size:.9375rem!important;white-space:normal!important;line-height:1.3}
.st-key-ma_composer{margin-top:.2rem}
.st-key-ma_actions [data-testid="stHorizontalBlock"]{display:grid!important;grid-template-columns:minmax(0,1fr) auto;gap:.75rem}
.st-key-ma_actions [data-testid="stColumn"]{width:100%!important;min-width:0!important}
.st-key-ma_actions [data-testid="stColumn"]:last-child{min-width:6rem!important}
.sera-brand{font-size:2rem;font-weight:700;letter-spacing:-1px;color:#223A36;margin:0 0 .5rem}
.sera-card-saved{font-size:.875rem;color:#1B6258;line-height:1.45;margin-top:.4rem}
.st-key-criteria_chips [data-testid="stHorizontalBlock"]{display:flex!important;flex-wrap:wrap;gap:.5rem}
.st-key-criteria_chips [data-testid="stColumn"]{width:auto!important;min-width:0!important;flex:0 1 auto!important}
.st-key-criteria_chips button{border-radius:999px!important;padding:.3rem .75rem!important;min-height:2.5rem}
.st-key-criteria_chips button p{font-size:.875rem!important}

.block-container{max-width:1000px;padding-top:1.1rem;padding-bottom:2rem}
.st-key-practice_grid,.st-key-saved_grid{container-type:inline-size}
:is(.st-key-practice_grid,.st-key-saved_grid) [data-testid="stHorizontalBlock"]{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr));gap:.9rem}
:is(.st-key-practice_grid,.st-key-saved_grid) [data-testid="stColumn"]{width:100%!important;min-width:0!important;flex:unset!important}
:is(.st-key-practice_grid,.st-key-saved_grid) [class*="st-key-practice_card_"] [data-testid="stHorizontalBlock"]{display:flex!important;gap:.4rem}
:is(.st-key-practice_grid,.st-key-saved_grid) [class*="st-key-practice_card_"] [data-testid="stColumn"]{width:auto!important;min-width:0!important;flex:1 1 0!important}
@container(max-width:760px){:is(.st-key-practice_grid,.st-key-saved_grid) [data-testid="stHorizontalBlock"]{grid-template-columns:repeat(2,minmax(0,1fr))}}
@container(max-width:460px){:is(.st-key-practice_grid,.st-key-saved_grid) [data-testid="stHorizontalBlock"]{grid-template-columns:1fr}}
h1{letter-spacing:-.8px;font-size:2rem!important}
h3{letter-spacing:-.2px}
.stButton button,.stPopover button{border-radius:9px;min-height:2.6rem}
.sera-steps{display:flex;gap:1.1rem;color:#49635C;font-size:.875rem;margin:.25rem 0 .85rem;flex-wrap:wrap}
.sera-steps span{padding:.35rem 0;border-bottom:2px solid transparent}
.sera-steps .active{color:#1B6258;border-color:#1B6258;font-weight:650}
.sera-card-meta{font-size:.875rem;color:#49635C;line-height:1.45}
.sera-card h3{font-size:1.1rem!important;line-height:1.35!important;min-height:2.7em;margin:.35rem 0 .55rem!important;padding:0!important;color:#223A36;overflow-wrap:anywhere}
.sera-status{display:inline-block;color:#1B6258;background:#EAF0ED;border-radius:5px;padding:.2rem .45rem;font-size:.875rem;line-height:1.4}
.sera-card-price{font-size:1.4rem;font-weight:650;letter-spacing:-.4px;margin-top:.6rem;color:#223A36;line-height:1.35;font-variant-numeric:tabular-nums}
.sera-card-fit{font-size:.875rem;color:#49635C;line-height:1.45;margin-top:.2rem;min-height:2.9em}
.sera-card-facts{font-size:.875rem;color:#49635C;margin:.4rem 0 .3rem;line-height:1.5;min-height:3em}
.sera-card-facts span{padding:0 .15rem}
.sera-card-gaps{font-size:.875rem;color:#49635C;line-height:1.45;margin:.4rem 0 .6rem}
[class*="st-key-practice_card_"]{border-radius:12px!important;padding:.9rem!important}
[class*="st-key-practice_card_"] button p{font-size:.875rem!important}
.st-key-detail_summary{container-type:inline-size;margin:.5rem 0 .2rem}
.st-key-detail_summary [data-testid="stHorizontalBlock"]{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr));gap:.6rem 1rem}
.st-key-detail_summary [data-testid="stColumn"]{width:100%!important;min-width:0!important;flex:unset!important}
.st-key-detail_summary [data-testid="stMetricValue"]{font-size:1.35rem!important;font-variant-numeric:tabular-nums;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;line-height:1.3}
.st-key-detail_summary [data-testid="stMetricLabel"]{font-size:.875rem!important;color:#49635C}
.sera-evidence-gaps{font-size:.875rem;color:#49635C;line-height:1.5;background:#EAF0ED;border-left:3px solid #1B6258;border-radius:5px;padding:.65rem .8rem;margin:.5rem 0 .8rem;overflow-wrap:anywhere}
.sera-evidence-gaps strong{color:#223A36}
[data-testid="stDialog"] [role="dialog"]{width:calc(100vw - 48px)!important;max-width:1000px!important;max-height:92dvh;overflow-y:auto}
[data-testid="stDialog"] h3{font-size:1.4rem!important;line-height:1.3}
[data-testid="stDialog"] [role="tablist"]{margin-top:.5rem;gap:.3rem}
@container(max-width:620px){.st-key-detail_summary [data-testid="stHorizontalBlock"]{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.st-key-ma_tasks [data-testid="stHorizontalBlock"]{grid-template-columns:1fr}.st-key-ma_tasks button{min-height:2.7rem}.block-container{padding:1rem}.sera-steps{gap:.7rem}.sera-card h3{min-height:0}.sera-card-facts,.sera-card-fit{min-height:0}.st-key-detail_summary [data-testid="stHorizontalBlock"]{grid-template-columns:repeat(2,minmax(0,1fr))}[data-testid="stDialog"] [role="dialog"]{position:fixed!important;inset:0!important;transform:none!important;box-sizing:border-box;background:#F7F9F8!important;width:100vw!important;max-width:100vw!important;height:100dvh!important;max-height:100dvh!important;margin:0!important;border-radius:0!important;overflow-y:auto}[data-testid="stDialog"] [role="tablist"]{overflow-x:auto;flex-wrap:nowrap}.sera-evidence-gaps{padding:.6rem .7rem}}
"""

APP_CSS = "<style>\n" + _APP_RULES + COMPARISON_CSS + "</style>"
