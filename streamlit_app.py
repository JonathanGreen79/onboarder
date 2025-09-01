import streamlit as st
import onboard as onboard  # your backend module with run_precheck()

st.set_page_config(page_title="LPG Pre-Check", layout="wide")


# ---------- helpers ----------
def reflow_paragraphs(text: str) -> str:
    """
    Collapse 'soft' line breaks into paragraphs and return a clean, wrapped string.
    We keep blank lines as paragraph separators.
    """
    if not text:
        return ""
    lines = [ln.rstrip() for ln in text.splitlines()]
    paras, buf = [], []
    for ln in lines:
        if not ln.strip():
            if buf:
                paras.append(" ".join(buf))
                buf = []
        else:
            buf.append(ln.strip())
    if buf:
        paras.append(" ".join(buf))
    return "\n\n".join(paras)


def boxed_markdown(md: str):
    """
    Render markdown in a pleasant pre-wrapped card.
    """
    st.markdown(
        """
        <style>
        .mdbox {
            padding: 16px;
            border: 1px solid #e6e6e6;
            background: #f8fafc;
            border-radius: 10px;
            white-space: pre-wrap;      /* wrap newlines */
            word-wrap: break-word;       /* break long words if needed */
            font-size: 0.95rem;
            line-height: 1.45;
        }
        .mdbox h4 {
            margin: 0 0 0.25rem 0;
            font-size: 1.02rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='mdbox'>{md}</div>", unsafe_allow_html=True)


# ---------- UI ----------
st.title("LPG Customer Tank — Location Intelligence Pre-Check")

words = st.text_input("Enter What3Words location:", "prefer.abandons.confining")

if st.button("Run Pre-Check"):
    try:
        result = onboard.run_precheck(words, generate_pdf=True)

        # Left / right columns
        col1, col2 = st.columns([1, 1.25])

        # LEFT: Summary (use markdown so it wraps nicely)
        with col1:
            st.subheader("Summary")
            # the backend returns plain-text; we can show it as a pre-wrapped block
            boxed_markdown(result.get("left_text", "").replace("  \n", "\n"))

        # RIGHT: AI commentary — reflow to remove soft breaks and format sections
        with col2:
            st.subheader("AI Commentary")

            # If your backend returns a fully formatted ai_text, just reflow it:
            ai_raw = result.get("ai_text", "")
            ai_clean = reflow_paragraphs(ai_raw)

            # Or, if your backend returns a dict of sections, you could re-compose here:
            # sections = result.get("ai_sections", {})
            # ai_clean = "\n\n---\n\n".join(
            #    f"**[{i}] {title}**\n\n{reflow_paragraphs(body)}"
            #    for i, title in enumerate(
            #        ["Safety Risk Profile", "Environmental Considerations",
            #         "Access & Logistics", "Overall Site Suitability"], 1)
            #    for body in [sections.get(title, "")]
            # )

            boxed_markdown(ai_clean)

        # PDF download (if produced)
        if result.get("pdf_path"):
            with open(result["pdf_path"], "rb") as f:
                st.download_button(
                    label="Download PDF report",
                    data=f,
                    file_name=result["pdf_path"].split("/")[-1],
                    mime="application/pdf",
                )

        # Map (if produced)
        if result.get("map_path"):
            st.image(result["map_path"], caption="Map", use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")
