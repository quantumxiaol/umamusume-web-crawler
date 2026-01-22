import numpy as np
from PIL import Image
from pathlib import Path

# 增加 PIL 读取大图的限制 (为了读取你的源 PNG)
Image.MAX_IMAGE_PIXELS = None 

def smart_image_to_pdf(
    image_path: Path, 
    pdf_path: Path, 
    max_page_height_ratio: float = 1.5, # 每一页的高度是宽度的 1.5 倍 (类似 A4 但稍微长一点)
    overlap: int = 0
) -> bool:
    """
    读取一张巨大的 PNG，智能切分为多页 PDF。
    避免切断文字，同时确保每一页的大小在 PIL 的处理范围内。
    """
    if not image_path.exists():
        return False

    try:
        # 打开图片
        img = Image.open(image_path).convert("RGB")
        width, total_height = img.size
        
        # 设定单页目标高度。假设宽度 1920，ratio 1.5，则每页高约 2880。
        # 这样一张 2.7亿像素(假设宽1920，高约14万)的图会被切成几十页，每页都很安全。
        target_height = int(width * max_page_height_ratio)
        
        # 转换为 numpy 数组进行快速分析
        # 注意：如果内存非常吃紧，这里可能需要分块读取，但一般机器 16GB 内存够用
        img_arr = np.asarray(img)
        
        pages = []
        current_y = 0
        
        print(f"Processing image: {width}x{total_height} (Target page height: ~{target_height})")

        while current_y < total_height:
            # 1. 确定本页的大致结束位置
            # 如果剩下的高度不足一页，直接收尾
            if total_height - current_y <= target_height:
                cut_y = total_height
            else:
                # 2. 在目标高度附近的“回溯区”寻找切割点
                # 我们在 [target_height * 0.8, target_height] 这个区间内从下往上找
                search_end_y = current_y + target_height
                search_start_y = int(current_y + target_height * 0.8)
                
                cut_y = -1
                
                # 为了性能和准确度，只分析水平中间 60% 的区域
                center_start = int(width * 0.2)
                center_end = int(width * 0.8)
                
                # 反向遍历 (寻找白色/纯色行)
                # 切片：img_arr[y, x_start:x_end, :]
                roi = img_arr[search_start_y:search_end_y, center_start:center_end, :]
                
                # 计算每一行的标准差 (Standard Deviation)
                # std < 5.0 通常意味着这一行颜色非常单一 (如白色背景)
                # axis=1 计算行的 std，再取 mean 简化判断
                stds = np.std(roi, axis=(1, 2)) 
                
                # 找到符合条件的行 (从下往上找，即 index 倒序)
                # np.where 返回的是相对于 roi 的索引
                candidates = np.where(stds < 10.0)[0]
                
                if len(candidates) > 0:
                    # 找到最靠下的切割点
                    best_local_y = candidates[-1]
                    cut_y = search_start_y + best_local_y
                else:
                    # 如果实在找不到(全是图)，被迫硬切
                    print(f"Warning: No clean cut found between {search_start_y} and {search_end_y}, forcing cut.")
                    cut_y = search_end_y

            # 3. 裁剪并保存
            # Crop box: (left, upper, right, lower)
            page_img = img.crop((0, current_y, width, cut_y))
            pages.append(page_img)
            
            print(f"  Added page: y={current_y} to {cut_y} (Height: {cut_y - current_y})")
            
            # 更新下一页起始位置
            current_y = cut_y - overlap
            
            if current_y >= total_height:
                break

        # 4. 保存为多页 PDF
        if pages:
            print(f"Saving {len(pages)} pages to PDF...")
            pages[0].save(
                pdf_path, 
                "PDF", 
                resolution=72.0, 
                save_all=True, 
                append_images=pages[1:]
            )
            return True
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False
    
    return False
