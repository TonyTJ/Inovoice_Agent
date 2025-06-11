from PIL import Image
from fuzzy_match import FuzzyMatchHandwriting
from fuzzy_match import FuzzyMatchPrint

def fuzzy_match_handwriting(name):
    Matcher = FuzzyMatchHandwriting()
    ocr_path = './workdir/{}_res.json'.format(name)
    Matcher.fuzzy_match(ocr_path)
    output_path = './workdir/{}_output.json'.format(name)
    Matcher.format_output(output_path)
    render_path = './workdir/{}_render.jpg'.format(name)
    src_path = './workdir/{}.jpg'.format(name)
    src_data = Image.open(src_path)
    Matcher.render_result(src_data, render_path)

def fuzzy_match_print(name):
    Matcher = FuzzyMatchPrint()
    ocr_path = './workdir/{}'.format(name)
    Matcher.fuzzy_match(ocr_path)
    output_path = './workdir/{}/output.json'.format(name)
    Matcher.format_output(output_path)
    # render_path = './workdir/{}_render.jpg'.format(name)
    # src_path = './workdir/{}.jpg'.format(name)
    # src_data = Image.open(src_path)
    # Matcher.render_result(src_data, render_path)


if __name__ == '__main__':
    name = 'oracle_order_chinese_1'
    fuzzy_match_handwriting(name)
    
