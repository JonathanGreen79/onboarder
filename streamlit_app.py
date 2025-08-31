import streamlit as st
import onboarder as onboard  # or: import lpg_precheck_pro as onboard

st.set_page_config(page_title="LPG Pre-Check", layout="wide")

st.title("LPG Customer Tank — Location Intelligence Pre-Check")

words = st.text_input("Enter What3Words location:", "prefer.abandons.confining")

if st.button("Run Pre-Check"):
    try:
        result = onboard.run_precheck(words, generate_pdf=True)

        col1, col2 = st.columns([1, 1.3])
        with col1:
            st.subheader("Summary")
            st.code(result["left_text"], language="text")
        with col2:
            st.subheader("AI Commentary")
            st.code(result["ai_text"], language="text")

        if result.get("pdf_path"):
            with open(result["pdf_path"], "rb") as f:
                st.download_button(
                    label="Download PDF report",
                    data=f,
                    file_name=result["pdf_path"].split("/")[-1],
                    mime="application/pdf",
                )

        if result.get("map_path"):
            st.image(result["map_path"], caption="Map", use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")
