# streamlit_app.py
import re
import streamlit as st
import onboard as onboard  # or: import lpg_precheck_pro as onboard


# ---------- small helpers ----------
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text or "")

def prewrap(text: str, *, font_size="0.95rem", line_height="1.45"):
    """Render a string with preserved newlines AND soft-wrapping."""
    if not text:
        return
    safe = strip_ansi(text)
    st.markdown(
        f"""
        <div style="
            white-space: pre-wrap;
            line-height: {line_height};
            font-size: {font_size};
            font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, Apple Color Emoji, Segoe UI Emoji;
        ">{safe}</div>
        """,
        unsafe_allow_html=True,
    )


# ---------- page ----------
st.set_page_config(page_title="LPG Pre-Check", layout="wide")
st.title("LPG Customer Tank — Location Intelligence Pre-Check")

# Default example can be anything valid; user can overwrite.
words = st.text_input("Enter What3Words location:", "prefer.abandons.confining")

if st.button("Run Pre-Check"):
    try:
        # Your backend does the heavy lifting and returns a dict:
        # {
        #   "left_text": "...", "ai_text": "...",
        #   "pdf_path": "precheck_abc.pdf" (optional),
        #   "map_path": "map_abc.png" (optional)
        #   ... (it can include other keys too)
        # }
        result = onboard.run_precheck(words, generate_pdf=True)

        # Layout: give the AI column a touch more width
        col1, col2 = st.columns([0.9, 1.1])

        with col1:
            st.subheader("Summary")
            prewrap(result.get("left_text", ""))

        with col2:
            st.subheader("AI Commentary")
            prewrap(result.get("ai_text", ""), font_size="0.96rem")

        # Optional map preview (if your backend saved one)
        if result.get("map_path"):
            st.image(result["map_path"], caption="Map", use_container_width=True)

        # PDF download (if produced)
        if result.get("pdf_path"):
            with open(result["pdf_path"], "rb") as f:
                st.download_button(
                    label="Download PDF report",
                    data=f,
                    file_name=result["pdf_path"].split("/")[-1],
                    mime="application/pdf",
                    type="secondary",
                )

    except Exception as e:
        st.error(f"Error: {e}")
