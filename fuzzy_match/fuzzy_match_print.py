from fuzzywuzzy import fuzz
import contextlib
import io
import os
import numpy as np

from .base import FuzzyMatchBase

def find_nearest(x, y, threshold=10):
    diff = np.abs(y - x)
    min_idx = np.argmin(diff)
    min_diff = diff[min_idx]
    return min_idx if min_diff <= threshold else None

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
        self.price = -1
        self.total_price = -1
        self.unit = None

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
        
    def fuzzy_match(self, path):
        ocr_results = self.load_pdf_ocr_result(path)
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

    def load_pdf_ocr_result(self, path):
        ocr_results = list()
        length = len(os.listdir(path))
        for i in range(length):
            page_path = os.path.join(path, str(i))
            for file in os.listdir(page_path):
                if file.endswith('.json'):
                    json_path = os.path.join(page_path, file)
                    ocr_result = self.load_ocr_result(json_path)
                    ocr_results.append(ocr_result)
        return ocr_results
    
    def load_customer_info(self, ocr_result, start_index=0):
        """
        目前读前n项，使用后一项'项次'做确认
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
        目前读customer_info后的7项，使用后一项是number做确认
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
                if key not in str_to_keys:
                    raise ValueError(f"未知的表头：{text}")
                key = str_to_keys[text]
                self.titles.append(key)
                self.title_left_position.append(item['box'][0])
                idx += 1
                continue
            break
        self.title_left_position = np.array(self.title_left_position)
        return idx
    
    def load_table_item(self, ocr_result, start_index=0):
        """
        按照box top pixel 位置来分割行，按行处理
        按照box left pixel 来确认text属于哪一列
        """
        idx = start_index
        while True:
            single_item = SingleItem()
            top = ocr_result[idx]['box'][1]
            while True:
                item = ocr_result[idx]
                if abs(item['box'][1] - top) > 10:
                    break
                left_position = item['box'][0]
                nearest_idx = find_nearest(left_position, self.title_left_position)
                if nearest_idx is None:
                    continue
                text = item['text']
                
           
    def build_fuzzy_match(self, template_items, name_to_id):
        """
        分别build 基于笔画和部首的模糊匹配器
        """
        template_item_name = [tup[0] for tup in list(name_to_id.keys())]
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.fcm_name_radical = fuzzychinese.FuzzyChineseMatch(analyzer='radical', ngram_range=(3, 3))
            self.fcm_name_radical.fit(template_item_name)
            self.fcm_name_stroke = fuzzychinese.FuzzyChineseMatch(analyzer='stroke', ngram_range=(3, 3))
            self.fcm_name_stroke.fit(template_item_name)

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
