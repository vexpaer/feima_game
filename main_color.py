"""
安装依赖：
    pip install opencv-python numpy scikit-learn

提取主色：
powershell运行：
    python main_color.py your_image.jpg
或者python调用函数：
    get_dominant_color("photo.jpg") 

兼容图片格式：jpg、jpeg、png（支持透明度）、bmp、tiff、gif、.webp

输出格式：
最终使用的主色: RGB(10, 36, 70)
颜色值: #0a2446
"""


import cv2
import numpy as np
from sklearn.cluster import KMeans


def extract_dominant_color(image_path, k=5):
    """
    提取图像主色，返回最终使用的主色 RGB
    """
    img = cv2.imread(image_path)

    if img is None:
        raise ValueError(f"无法读取图片: {image_path}")

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w, _ = img_rgb.shape

    # 降采样加速
    scale = min(1, 300 / max(h, w))
    new_size = (int(w * scale), int(h * scale))
    img_small = cv2.resize(img_rgb, new_size, interpolation=cv2.INTER_AREA)

    pixels = img_small.reshape(-1, 3)

    # 防止图片太小导致聚类数量超过像素数量
    k = min(k, len(pixels))

    # K-Means 聚类
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(pixels)
    centers = kmeans.cluster_centers_.astype(int)

    counts = np.bincount(labels)
    total = len(labels)

    # 合并相似色
    merged_colors = []
    merged_counts = []
    used = [False] * k

    for i in range(k):
        if used[i]:
            continue

        color_sum = centers[i].astype(float) * counts[i]
        count_sum = counts[i]
        used[i] = True

        for j in range(i + 1, k):
            if not used[j]:
                color_diff = np.sqrt(
                    np.sum((centers[i].astype(float) - centers[j].astype(float)) ** 2)
                )

                if color_diff < 40:
                    color_sum += centers[j].astype(float) * counts[j]
                    count_sum += counts[j]
                    used[j] = True

        merged_color = (color_sum / count_sum).astype(int)

        merged_colors.append(merged_color)
        merged_counts.append(count_sum)

    merged_colors = np.array(merged_colors)
    merged_counts = np.array(merged_counts)

    def get_saturation(rgb):
        r, g, b = rgb / 255.0
        mx = max(r, g, b)
        mn = min(r, g, b)

        if mx == 0:
            return 0

        return (mx - mn) / mx

    def get_brightness(rgb):
        return max(rgb) / 255.0

    valid_colors = []
    scores = []

    for color, count in zip(merged_colors, merged_counts):
        sat = get_saturation(color)
        bright = get_brightness(color)

        # 过滤太亮、太暗、太灰的颜色
        if bright > 0.93 or bright < 0.05 or sat < 0.08:
            continue

        area_ratio = count / total

        # 面积占比 + 饱和度 + 明度适中
        brightness_score = 1.0 - abs(bright - 0.55) * 2
        score = 0.60 * area_ratio + 0.25 * sat + 0.15 * max(0, brightness_score)

        valid_colors.append(color)
        scores.append(score)

    # 如果没有符合条件的颜色，就使用面积最大的颜色
    if len(valid_colors) == 0:
        best_idx = np.argmax(merged_counts)
        best_color = merged_colors[best_idx]
    else:
        best_idx = np.argmax(scores)
        best_color = valid_colors[best_idx]

    return tuple(int(x) for x in best_color)


def main():
    import sys

    if len(sys.argv) < 2:
        print("用法: python dominant_color.py <图片路径> [R G B]")
        print("示例:")
        print("  自动提取主色: python dominant_color.py photo.png")
        print("  指定主色: python dominant_color.py photo.png 100 150 200")
        return

    input_path = sys.argv[1]

    # 如果手动指定 RGB，就直接使用指定颜色
    if len(sys.argv) >= 5:
        try:
            r = int(sys.argv[2])
            g = int(sys.argv[3])
            b = int(sys.argv[4])
            used_color = (r, g, b)
        except ValueError:
            print("颜色参数格式错误，改为自动提取主色")
            used_color = extract_dominant_color(input_path)
    else:
        used_color = extract_dominant_color(input_path)

    print(f"最终使用的主色: RGB{used_color}")
    print(f"颜色值: #{used_color[0]:02x}{used_color[1]:02x}{used_color[2]:02x}")


if __name__ == "__main__":
    main()