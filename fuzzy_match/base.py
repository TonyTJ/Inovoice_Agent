import pandas as pd
import numpy as np
import re
import json
from PIL import Image, ImageDraw, ImageFont

def draw_chinese_text_in_box(img, text, box_coords, font_path="resource/wqy-zenhei.ttc", text_color=(0, 0, 0), bg_color=None):
    """
    Draw Chinese text inside a specified box on an image.
    
    Args:
        img_path (str): Path to the input image.
        text (str): Chinese text to draw.
        box_coords (tuple): (x1, y1, x2, y2) coordinates of the box.
        font_path (str): Path to a Chinese font file (e.g., simhei.ttf).
        text_color (tuple): RGB color for the text.
        bg_color (tuple): Optional background color for the box.
    """
    # Open the image
    draw = ImageDraw.Draw(img)
    
    # Extract box dimensions
    x1, y1, x2, y2 = box_coords
    box_width = x2 - x1
    box_height = y2 - y1
    
    # Start with a large font size and reduce until text fits
    font_size = 50  # Initial guess
    font = ImageFont.truetype(font_path, font_size, encoding="utf-8")
    
    # Adjust font size to fit the box
    while True:
        # pillow <= 9.5.0
        # text_width, text_height = draw.textsize(text, font=font)
        # pillow >= 10.0.0
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1] 
        if text_width <= box_width and text_height <= box_height:
            break
        font_size -= 1
        font = ImageFont.truetype(font_path, font_size, encoding="utf-8")
    
    # Calculate centered position
    text_x = x1 + (box_width - text_width) // 2
    text_y = y1 + (box_height - text_height) // 2
    
    # Optional: Draw background (if needed)
    if bg_color:
        draw.rectangle(box_coords, fill=bg_color)
    
    # Draw the text
    draw.text((text_x, text_y), text, fill=text_color, font=font)
    
    return img

class FuzzyMatchBase:
    def __init__(self):
        self.customer_name = None
        self.order_date = None
        self.status = None
        self.template_path = './resource/客戶訂單資料.xlsx'
        self.load_items()
        self.build_fuzzy_match(self.template_items, self.name_to_id)

    def load_items(self):
        """订单资料存在重复品号以及品号下多个品名情况，先处理成独立的词
        处理逻辑：品名按照正斜杠与反斜杠做分隔，品名+单位绑定为一个元组，映射到一个品号id
        如果品名+单位有重复，只保留第一个
        """
        ITEMS = dict()
        NAME_to_ID = dict()
        df = pd.read_excel(self.template_path, engine='openpyxl')
        for index, row in df.iterrows():
            id = row['品號']
            if not isinstance(id, str) and np.isnan(id):
                continue
            ITEMS.setdefault(id, dict())
            ITEMS[id].setdefault('name', set())
            if row['品名'] is not None:
                results = re.split(r'[\\/]', str(row['品名']))
            else:
                # results = []
                print("Error Result ", results)
                continue
            unit = row['單位']
            if unit == 'KG':
                unit = '斤'
            for result in results:
                result = result.strip()
                result_unit = (result, unit)
                ITEMS[id]['name'].add(result_unit)
                if result_unit not in NAME_to_ID:
                    NAME_to_ID[result_unit] = id
                elif NAME_to_ID[result_unit] != id:
                    print(f"品名 {result_unit} 重复，请确认品号 {NAME_to_ID[result_unit], id}")
                else:
                    pass
        self.template_items = ITEMS
        self.name_to_id = NAME_to_ID

    def load_ocr_result(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            ocr_result = json.load(f)
        ocr_texts = ocr_result['rec_texts']
        ocr_scores = ocr_result['rec_scores']
        ocr_boxes = ocr_result['rec_boxes']
        return [dict(text=text, score=score, box=box) for text, score, box in zip(ocr_texts, ocr_scores, ocr_boxes)]

    def render_result(self, src_data, output_path):
        img = src_data
        state2color = {
            'normal': (0, 255, 0),
            'warning': (180, 180, 0),
            'error': (255, 0, 0)
        }
        width, height = img.size
        ocr_result_image = Image.new('RGB', (width, height), color='white')
        match_result_image = Image.new('RGB', (width, height), color='white')
        for item in self.items:
            box = item.box
            state_ocr = 'normal'
            if item.ocr_warning is not None:
                state_ocr = 'warning'
            if item.ocr_error is not None:
                state_ocr = 'error'
            color_ocr = state2color[state_ocr]
            ocr_result_image = draw_chinese_text_in_box(ocr_result_image, item.ocr_text, box, text_color=color_ocr)

            state = 'normal'
            if item.warning is not None:
                state = 'warning'
            if item.error is not None:
                state = 'error'
            color = state2color[state]
            match_result_image = draw_chinese_text_in_box(match_result_image, item.final_text, box, text_color=color)

        final_img = Image.new('RGB', (width * 3, height))    
        final_img.paste(img, (0, 0))
        final_img.paste(ocr_result_image, (width, 0))
        final_img.paste(match_result_image, (width * 2, 0))
        final_img.save(output_path)

    def format_output(self, output_path):
        output = {
            "customer_name": None,
            "order_date": None,
            "items": [],
            "status": None
        }
        for item in self.items:
            output['items'].append(item.format_output())
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=4)