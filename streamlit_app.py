import streamlit as st
import onboard  # your main file onboard.py

st.set_page_config(page_title="LPG Pre-Check", layout="wide")

st.title("LPG Customer Tank — Location Intelligence Pre-Check")

words = st.text_input("Enter What3Words location:", "prefer.abandons.confining")

if st.button("Run Pre-Check"):
    result = onboard.run_precheck(words, generate_pdf=True)  # wrap in a function
    st.success("✅ Pre-check complete!")

    st.text(result.get("summary", "No summary produced."))

    if "pdf_path" in result:
        with open(result["pdf_path"], "rb") as f:
            st.download_button("Download PDF report", f, file_name="lpg_precheck.pdf")
