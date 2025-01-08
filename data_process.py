import os
import shutil
from pathlib import Path

# 定义路径
base_path = Path("./data/hexiao/hsi-detect/dataset/hsidetection/")
label_path = base_path / "sa_information/labels/train"
img_path = base_path / "sa_information/images/train"
label_path1 = base_path / "se_information/labels/train"
img_path1 = base_path / "se_information/images/train"
output_label_path = base_path / "sa_information/labels/train1"
output_img_path = base_path / "sa_information/images/train1"
output_label_path1 = base_path / "se_information/labels/train1"
output_img_path1 = base_path / "se_information/images/train1"

# 创建输出文件夹
output_label_path.mkdir(parents=True, exist_ok=True)
output_img_path.mkdir(parents=True, exist_ok=True)
output_label_path1.mkdir(parents=True, exist_ok=True)
output_img_path1.mkdir(parents=True, exist_ok=True)

# 遍历标签文件夹
for filename in os.listdir(label_path):
    if filename.endswith(".txt"):
        # 定义文件路径
        file_path = label_path / filename
        file_path1 = label_path1 / filename
        img_filename = filename.replace(".txt", ".jpg")
        img_filename1 = filename.replace(".txt", ".png")
        img_file_path = img_path / img_filename
        img_file_path1 = img_path1 / img_filename1

        print(f"处理 {filename}")

        # 读取文件内容
        with open(file_path, "r") as f:
            data = f.readlines()
        with open(file_path1, "r") as g:
            data1 = g.readlines()

        # 检查是否包含标签 2
        contains_label_2 = any(line.startswith("2") for line in data)
        if contains_label_2:
            print(f"剔除 {filename}")
            continue

        # 更新标签
        updated_data = []
        updated_data1 = []
        for line in data:
            parts = line.strip().split(" ")
            label = int(parts[0])
            if label > 2:
                parts[0] = str(label - 1)
            updated_data.append(" ".join(parts))
        for line in data1:
            parts = line.strip().split(" ")
            label = int(parts[0])
            if label > 2:
                parts[0] = str(label - 1)
            updated_data1.append(" ".join(parts))

        # 保存标签文件
        output_label_file = output_label_path / filename
        output_label_file1 = output_label_path1 / filename
        with open(output_label_file, "w") as f:
            f.write("\n".join(updated_data))
        with open(output_label_file1, "w") as g:
            g.write("\n".join(updated_data1))

        # 复制图像文件
        if img_file_path.exists():
            shutil.copy(img_file_path, output_img_path / img_filename)
            print(f"保存 {filename} 和对应图像")
        if img_file_path1.exists():
            shutil.copy(img_file_path1, output_img_path1 / img_filename)
            print(f"保存 {filename} 和对应图像")

print("处理完成")
#####################################
#####################################
# #####################################
# import os
#
# # 标签文件路径
# label_path = r"./data/hexiao/hsi-detect/dataset/hsidetection/sa_information/labels/test"
#
# # 遍历标签文件夹中的所有文件
# for filename in os.listdir(label_path):
#     if filename.endswith(".txt"):  # 只处理 .txt 文件
#         file_path = os.path.join(label_path, filename)
#         print(f"正在处理 {filename}")
#
#         # 读取文件内容
#         with open(file_path, "r") as f:
#             data = f.readlines()
#
#         # 更新标签（类减 1）
#         updated_data = []
#         for line in data:
#             parts = line.strip().split(" ")
#             label = int(parts[0])  # 获取标签类别
#             if label >2:
#
#                 parts[0] = str(label -1)  # 标签减 1
#             updated_data.append(" ".join(parts))
#
#         # 将修改后的内容写回原文件
#         with open(file_path, "w") as f:
#             f.write("\n".join(updated_data))
#
# print("所有标签文件已更新完毕！")
