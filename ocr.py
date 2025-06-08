from paddleocr import PaddleOCR

ocr = PaddleOCR(device="gpu") # 通过 device 参数使得在模型推理时使用 GPU
ocr = PaddleOCR(
    text_detection_model_name="PP-OCRv5_server_det",
    text_recognition_model_name="PP-OCRv5_server_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
) # 更换 PP-OCRv5_server 模型

    
if __name__ == "__main__":
    # path = './workdir/c1a3f7e2-9893-4fe3-a509-46b31007696c.jpg'
    path = './resource/oracle_order_chinese_1.pdf'
    result = ocr.predict(path)
    for res in result:
        res.print()
        res.save_to_img("workdir")
        res.save_to_json("workdir")