import fuzzychinese
import re
import contextlib
import io

from .base import FuzzyMatchBase

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

class FuzzyMatchHandwriting(FuzzyMatchBase):
    def __init__(self):
        super().__init__()
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
                item.ocr_error = "ocr score < 0.5"
            self.items.append(item)
                
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
