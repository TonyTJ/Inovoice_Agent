import pandas as pd
import numpy as np
import fuzzychinese
import re
import json
import contextlib
import io
from PIL import Image, ImageDraw, ImageFont

def split_ocr_row(text):
    # Updated pattern to capture mixed quantity+unit blocks
    pattern = re.compile(r"""
        ^\s*
        (?P<item>[\u4e00-\u9fa5A-Za-z]+?)                    # Non-greedy match of item name
        (?P<quantity>[0-9×xX*＋+]+(?:[\d×xX*＋+]+)?)?           # Match quantity that includes math expressions
        (?P<unit>[\u4e00-\u9fa5]+)?\s*$                      # Optional unit in Chinese characters
    """, re.VERBOSE)

    match = pattern.match(text.strip())
    result = {
        "item": "",
        "quantity": "",
        "unit": ""
    }

    if match:
        result["item"] = match.group("item") or ""
        result["quantity"] = match.group("quantity") or ""
        result["unit"] = match.group("unit") or ""

        # Warning: overly long numeric segment may indicate OCR merge
        if re.search(r"\d+[×xX*＋+]\d{4,}", result["quantity"]):
            result["warning"] = "suspicious quantity format"

        # Warning: quantity present in later segment (e.g., 10斤3×3)
        if re.search(r"\d[\u4e00-\u9fa5]+\d", text):
            result["warning"] = "compound quantity+unit likely"
    else:
        # Attempt fallback: extract item, rest = quantity+unit
        fallback_match = re.match(r"([\u4e00-\u9fa5A-Za-z]+)(.*)", text.strip())
        if fallback_match:
            result["item"] = fallback_match.group(1)
            tail = fallback_match.group(2)
            qty_unit_match = re.match(r"([0-9×xX*＋+]+)([\u4e00-\u9fa5]*)", tail)
            if qty_unit_match:
                result["quantity"] = qty_unit_match.group(1)
                result["unit"] = qty_unit_match.group(2)
                # result["error"] = "fallback partial parse"
            else:
                result["error"] = "cannot parse quantity/unit segment"
        else:
            result["error"] = "unmatched format"

    return result

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
        text_width, text_height = draw.textsize(text, font=font)
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

class SingleItem:
    def __init__(self):
        self.product_id = None
        self.matched_name = None
        self.origin_input = None
        self.quantity = -1
        self.match_score = -1
        self.ocr_score = -1
        self.box = None
        self.ocr_text = None
        self.final_text = None
        self.warning = None
        self.error = None
        self.ocr_warning = None
        self.ocr_error = None

    def format_output(self):
        return {
            'product_id': self.product_id,
            'matched_name': self.matched_name,
            'origin_input': self.origin_input,
            'quantity': self.quantity,
            'match_score': float(self.match_score),
        }

class FuzzyMatch:
    def __init__(self):
        self.template_path = './resource/客戶訂單資料.xlsx'
        self.load_items()
        self.build_fuzzy_match(self.template_items, self.name_to_id)
    
    def fuzzy_match(self, path):
        ocr_results = self.load_ocr_result(path)
        ocr_results = self.fuzzy_match_ocr_single(ocr_results)
        self.items = list()
        for result in ocr_results:
            item = SingleItem()
            item.product_id = self.name_to_id.get((result['matched_name'], result['unit']), None)
            item.matched_name = result['matched_name']
            item.origin_input = result['item']
            item.quantity = result['quantity']
            item.match_score = result['match_score']
            item.ocr_score = result['score']
            item.box = result['box']
            item.ocr_text = result['text']
            item.final_text = result['matched_name'] + ' ' + result['quantity'] + ' ' +  result['unit']
            item.warning = result.get('warning', None)
            item.error = result.get('error', None)
            if item.match_score < 0.8:
                item.warning = "match score < 0.8"
            if item.ocr_score < 0.75:
                item.ocr_warning = "ocr score < 0.75"
            if item.match_score < 0.65:
                item.error = "match score < 0.65"
            if item.ocr_score < 0.5:
                item.ocr_error = "ocr score < 0.6"
            self.items.append(item)

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
                
    def build_fuzzy_match(self, ITEMS, NAME_to_ID):
        """
        分别build 品号与品名的模糊匹配器
        """
        template_item_name = [tup[0] for tup in list(NAME_to_ID.keys())]
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.fcm_name_radical = fuzzychinese.FuzzyChineseMatch(analyzer='radical', ngram_range=(3, 3))
            self.fcm_name_radical.fit(template_item_name)
            self.fcm_name_stroke = fuzzychinese.FuzzyChineseMatch(analyzer='stroke', ngram_range=(3, 3))
            self.fcm_name_stroke.fit(template_item_name)

    def load_ocr_result(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            ocr_result = json.load(f)
        ocr_texts = ocr_result['rec_texts']
        ocr_scores = ocr_result['rec_scores']
        ocr_boxes = ocr_result['rec_boxes']
        return [dict(text=text, score=score, box=box) for text, score, box in zip(ocr_texts, ocr_scores, ocr_boxes)]

    def fuzzy_match_ocr_single(self, ocr_results):
        for row in ocr_results:
            result = split_ocr_row(row['text'])
            row.update(result)
            if row.get('item', None) is None:
                continue
            ocr_item_name = row['item']
            with contextlib.redirect_stdout(io.StringIO()):
                fuzzy_result_stroke = self.fcm_name_stroke.transform([ocr_item_name])[0]
                similarity_scores_stroke = self.fcm_name_stroke.get_similarity_score()[0]

                fuzzy_result_radical = self.fcm_name_radical.transform([ocr_item_name])[0]
                similarity_scores_radical = self.fcm_name_radical.get_similarity_score()[0]
            # print(f"OCR识别结果：{ocr_item_name}，模糊匹配结果：{fuzzy_result}, 相似度分数：{similarity_scores}")
            
            stroke_scores = {}
            radical_scores = {}
            
            # fuzzy chinese transform 返回结果可能存在重复元素，需要去重处理
            for item, score in zip(fuzzy_result_stroke, similarity_scores_stroke):
                if item not in stroke_scores or score > stroke_scores[item]:
                    stroke_scores[item] = score
            
            for item, score in zip(fuzzy_result_radical, similarity_scores_radical):
                if item not in radical_scores or score > radical_scores[item]:
                    radical_scores[item] = score
            
            # 综合两组评分
            combined_scores = {}
            all_items = set(stroke_scores.keys()) | set(radical_scores.keys())
            
            for item in all_items:
                stroke_score = stroke_scores.get(item, 0)
                radical_score = radical_scores.get(item, 0)
                combined_scores[item] = max(stroke_score, radical_score) + min(stroke_score, radical_score) / 10
            
            sorted_items = sorted(combined_scores.keys(), 
                                key=lambda x: combined_scores[x], 
                                reverse=True)
            sorted_scores = [combined_scores[item] for item in sorted_items]
    
            row['matched_name'] = sorted_items[0]
            row['match_score'] = sorted_scores[0] if sorted_scores[0] < 1.0 else 1.0
        return ocr_results
    
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
 
if __name__ == '__main__':
    Matcher = FuzzyMatch()
    ocr_path = './workdir/c1a3f7e2-9893-4fe3-a509-46b31007696c_res.json'
    Matcher.fuzzy_match(ocr_path)
    output_path = './workdir/c1a3f7e2-9893-4fe3-a509-46b31007696c_output.json'
    Matcher.format_output(output_path)
    render_path = './workdir/c1a3f7e2-9893-4fe3-a509-46b31007696c_render.jpg'
    src_path = './workdir/c1a3f7e2-9893-4fe3-a509-46b31007696c.jpg'
    src_data = Image.open(src_path)
    Matcher.render_result(src_data, render_path)
