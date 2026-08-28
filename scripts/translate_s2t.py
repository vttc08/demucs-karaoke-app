import opencc
import json 

cc = opencc.OpenCC('s2t')

zhcn_file = "locales/zh-CN.json"
zh_tw_file = "locales/zh-TW.json"

def convert_zhcn_to_zhtw():
    with open(zhcn_file, 'r', encoding='utf-8') as f:
        zhcn_data = json.load(f)

    zhtw_data = {}
    for key, value in zhcn_data.items():
        if isinstance(value, str):
            zhtw_data[key] = cc.convert(value)
        else:
            zhtw_data[key] = value

    with open(zh_tw_file, 'w', encoding='utf-8') as f:
        json.dump(zhtw_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    convert_zhcn_to_zhtw()
    print(f"Converted {zhcn_file} to {zh_tw_file} using OpenCC.")