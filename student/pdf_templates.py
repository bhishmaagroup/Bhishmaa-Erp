from reportlab.platypus import Image
from reportlab.lib.units import inch
import os

def pdf_image(path, w=1.2*inch, h=1.4*inch):
    """
    Safely load image for PDF.
    """
    if path and os.path.exists(path):
        return Image(path, width=w, height=h)
    return ""
