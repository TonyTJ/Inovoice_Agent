from paddleocr import PaddleOCR
import fitz
from PIL import Image
import numpy as np

ocr = PaddleOCR(
    device="gpu",
    det_db_unclip_ratio=2.0,
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
) # 更换 PP-OCRv5_server 模型

def pdf_to_images(pdf_path, dpi=300):
    doc = fitz.open(pdf_path)
    images = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72), alpha=False)  # 设置分辨率
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(np.array(img))
    doc.close()
    return images

if __name__ == "__main__":
    path = './resource/sap_order_chinese_4.pdf'
    # path = './resource/oracle_order_chinese_1.pdf'
    imgs = pdf_to_images(path, dpi=300)
    for idx, img in enumerate(imgs):
        result = ocr.predict(img)
        # for idx, res in enumerate(result):
            # res.print()
        result[0].save_to_img("workdir/sap_order_chinese_4/{}".format(idx))
        result[0].save_to_json("workdir/sap_order_chinese_4/{}".format(idx))