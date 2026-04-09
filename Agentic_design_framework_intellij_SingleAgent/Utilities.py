# Extracts and returns all text from text files.
import PyPDF2


def file_to_string(filepath):
    text = ""
    with open(filepath, 'r') as file:
        text += file.read() + "\n"
    return text


# Extracts and returns all text from pdf files.
def extract_text_from_pdf(pdf_path):
    # Extracts and returns all text from the specified PDF file.
    text = ""
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text