import fuzzywuzzy
import re
import os
import fuzzywuzzy.process
import numpy as np
from copy import deepcopy
import pandas as pd
from .base import FuzzyMatchBase, draw_chinese_text_in_box
from PIL import Image, ImageDraw, ImageFont

class SingleItem:
    def __init__(self):
        self.product_id = None
        self.matched_name = None
        self.origin_input = None
        self.quantity = None
        self.match_score = -1
        self.ocr_score = -1
        self.box = None
        self.ocr_text = ''
        self.final_text = ''
        self.warning = None
        self.error = None
        self.ocr_warning = None
        self.ocr_error = None
        self.price = None
        self.total_price = None
        self.unit = None
        self.product_name = None
        self.row_text = None
        self.page_index = -1

    def format_output(self):
        return {
            'product_id': self.product_id,
            'matched_name': self.matched_name,
            'origin_input': self.origin_input,
            'quantity': self.quantity,
            'match_score': float(self.match_score),
        }

class FuzzyMatchPrint(FuzzyMatchBase):
    """
    基于打印字的模糊匹配器
    属性的对齐规则，以及用户信息的提取规则基于提供的pdf作为模板设计
    """
    def __init__(self):
        super().__init__()
        self.titles = list()
        self.title_left_position = list()
        self.items = list()
        
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
                result_unit = (row['品名'], row['單位'])
                ITEMS[id]['name'].add(result_unit)
                if result_unit not in NAME_to_ID:
                    NAME_to_ID[result_unit] = id
                elif NAME_to_ID[result_unit] != id:
                    print(f"品名 {result_unit} 重复，请确认品号 {NAME_to_ID[result_unit], id}")
                else:
                    pass
        self.template_items = ITEMS
        self.name_to_id = NAME_to_ID
        
    def fuzzy_match(self, path_list):
        ocr_results = self.load_pdf_ocr_result(path_list)
        self.parse_ocr_results(ocr_results)
        names = list(self.name_to_id.keys())
        for item in self.items:
            item.origin_input = item.product_name
            if item.product_id is not None and item.product_name is not None:
                result = fuzzywuzzy.process.extract(item.product_name, names, limit=5)
                if item.product_id in self.template_items:
                    name_matched_id = False
                    for candidate in result:
                        candidate_name = candidate[0][0]
                        if item.product_id == self.name_to_id[candidate[0]]:
                            item.matched_name = candidate_name
                            item.match_score = candidate[1] / 100.0
                            name_matched_id = True
                            break
                        else:
                            pass
                    if not name_matched_id:
                        item.error = "Product ID and name do not match"
                        item.match_score = 0.0
                else:
                    item.error = "Product ID not found in customer template"
                    item.match_score = 0.0
                    item.product_id = None
            else:
                item.error = "Missing product ID or name"
            if item.product_id is not None:
                item.final_text += item.product_id + ' - '
            if item.matched_name is not None:
                item.final_text += item.matched_name + ' - '
            if item.quantity is not None:
                item.final_text += str(item.quantity) + ' - '
            if item.unit is not None:
                item.final_text += item.unit + ' - '
            if item.price is not None:
                item.final_text += str(item.price) + ' - '
            if item.total_price is not None:
                item.final_text += str(item.total_price) + ' - '
                
            if item.ocr_score < 0.75:
                item.ocr_warning = "ocr score < 0.75"
            if item.ocr_score < 0.5:
                item.ocr_error = "ocr score < 0.5"
            if item.quantity is None:
                item.error = "Unrecognizable quantity"

    def load_pdf_ocr_result(self, path_list):
        ocr_results = list()
        for path in path_list:
            ocr_result = self.load_ocr_result(path)
            ocr_results.append(ocr_result)
        
        return ocr_results
    
    def parse_ocr_results(self, ocr_results):
        """
        处理多页的pdf信息，目前的强假设：
        1.第一页表头包含客户信息
        2.第一页含有表头，且表头与项对齐
        3.非item的信息只在结尾部分（金额，状态等）
        """
        start_index = 0
        first_page_result = ocr_results[0]
        start_index = self.load_customer_info(first_page_result, start_index)
        start_index = self.load_table_title(first_page_result, start_index)
        self.load_table_item(ocr_results[0], 0, start_index)
        for i in range(1, len(ocr_results)):
            self.load_table_item(ocr_results[i], i, 0)
        
    
    def load_customer_info(self, ocr_result, start_index=0):
        """
        目前读前n项，使用后一项'項次'做确认
        """
        end_str = ["項次"]
        customer_str = ["客戶代號", "請款對象"]
        date_str = ["訂單日期"]
        idx = start_index
        while True:
            item = ocr_result[idx]
            text = item['text']
            if any(x in text for x in end_str):
                break
            if any(x in text for x in customer_str):
                self.customer_name = text.split(':')[-1]
            if any(x in text for x in date_str):
                self.order_date = text.split(':')[-1]
            idx += 1
        return idx

    def load_table_title(self, ocr_result, start_index=0):
        """
        目前读customer_info后的7项
        """
        str_to_keys = {
            "項次": "index",
            "品號": "product_id",
            "品名": "product_name",
            "數量": "quantity",
            "單位": "unit",
            "單價": "price",
            "小計": "total_price",
        }
        idx = start_index
        while True:
            item = ocr_result[idx]
            text = item['text']
            if any(x in text for x in list(str_to_keys.keys())):
                if text not in str_to_keys:
                    raise ValueError(f"未知的表头：{text}")
                self.titles.append(str_to_keys[text])
                self.title_left_position.append(item['box'][0])
                idx += 1
                continue
            break
        self.title_left_position = np.array(self.title_left_position)
        return idx
    
    def load_table_item(self, origin_ocr_result, page_index, start_index=0):
        """
        按照box top pixel 位置来分割行，按行处理
        按照box left pixel 来确认text属于哪一列
        """
        ocr_result = deepcopy(origin_ocr_result[start_index:])
        ocr_result.sort(key=lambda x: x['box'][1])
        
        current_row = []
        previous_top = None
        
        for res in ocr_result:
            top = res['box'][1]
            if previous_top is not None and abs(top - previous_top) > 15:
                if len(current_row) <= 2:
                    item = self.process_special_row(current_row)
                    if item:
                        item.page_index = page_index
                        self.items.append(item)
                    current_row = []
                else:
                    item = self.process_row(current_row)
                    item.page_index = page_index
                    self.items.append(item)
                    current_row = []
            
            current_row.append(res)
            previous_top = top
        
        if current_row:
            if len(current_row) <= 2:
                item = self.process_special_row(current_row)
                if item:
                    item.page_index = page_index
                    self.items.append(item)
            else:
                item = self.process_row(current_row)
                item.page_index = page_index
                self.items.append(item)

    def process_row(self, row_data):
        """
        Process a single row of OCR results and create a SingleItem object.
        """
        item = SingleItem()
        row_box = [float('inf'), float('inf'), float('-inf'), float('-inf')]  # [x1, y1, x2, y2]
        row_data = sorted(row_data, key=lambda res: res['box'][0])

        for res in row_data:
            text = res['text']
            score = res['score']
            item.ocr_text += text + ' - '
            left = res['box'][0]
            top = res['box'][1]
            right = res['box'][2]
            bottom = res['box'][3]
            
            row_box[0] = min(row_box[0], left)
            row_box[1] = min(row_box[1], top)
            row_box[2] = max(row_box[2], right)
            row_box[3] = max(row_box[3], bottom)
            
            column_index = self.get_column_index(left, self.title_left_position)
            
            if column_index is None:
                item.warning = f"Text '{text}' has an unrecognized position."
                continue
            
            column_name = self.titles[column_index]
            setattr(item, column_name, text)
            if column_name in ['quantity','product_id', 'product_name']:
                if item.ocr_score == -1:
                    item.ocr_score = score
                else:
                    item.ocr_score = min(item.ocr_score, score)
        
        item.box = row_box
        
        if not item.product_id:
            item.error = "Missing product ID"
        if not item.product_name:
            item.error = "Missing product name"
        return item
    
    def process_special_row(self, row_data):
        text = row_data[0]['text']
        if "總金額" in text:
            numbers = re.findall(r'\d+\.?\d*', text)
            self.order_price = float(numbers[0])
        elif "稅額" in text:
            pass
        elif "狀態" in text:
            self.order_status = text.split(':')[-1]
        else:
            pass
            # item = SingleItem()
            # row_box = [float('inf'), float('inf'), float('-inf'), float('-inf')]  # [x1, y1, x2, y2]
            # for res in row_data:
            #     text = res['text']
            #     left = res['box'][0]
            #     top = res['box'][1]
            #     right = res['box'][2]
            #     bottom = res['box'][3]
                
            #     row_box[0] = min(row_box[0], left)
            #     row_box[1] = min(row_box[1], top)
            #     row_box[2] = max(row_box[2], right)
            #     row_box[3] = max(row_box[3], bottom)
            #     item.ocr_text += text + ' '
            # item.box = row_box
            # item.error = "Unrecognized special row"
            # return item

    def get_column_index(self, left_position, title_left_position, threshold=10):
        diff = np.abs(left_position - title_left_position)
        min_idx = np.argmin(diff)
        min_diff = diff[min_idx]
        return min_idx if min_diff <= threshold else None
    
    def render_result(self, src_list):
        origin_imgs = list()
        ocr_imgs = list()
        match_imgs = list()
        state2color = {
            'normal': (0, 255, 0),
            'warning': (180, 180, 0),
            'error': (255, 0, 0)
        }
        for src in src_list:
            img = Image.open(src)
            origin_imgs.append(img)
            width, height = origin_imgs[0].size
            ocr_result_image = Image.new('RGB', (width, height), color='white')
            match_result_image = Image.new('RGB', (width, height), color='white')
            ocr_imgs.append(ocr_result_image)
            match_imgs.append(match_result_image)
            
        for item in self.items:
            ocr_result_image = ocr_imgs[item.page_index]
            match_result_image = match_imgs[item.page_index]
            
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
            
        for origin_img, ocr_img, match_img, src_path in zip(origin_imgs, ocr_imgs, match_imgs, src_list):
            final_img = Image.new('RGB', (width*3, height))
            final_img.paste(origin_img, (0, 0))
            final_img.paste(ocr_img, (width, 0))
            final_img.paste(match_img, (width*2, 0))
            render_path = src_path.replace('src', 'render')
            if not os.path.exists(os.path.dirname(render_path)):
                os.makedirs(os.path.dirname(render_path))
            final_img.save(render_path)
            
            