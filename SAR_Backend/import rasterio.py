import rasterio
from rasterio.windows import Window
from rasterio.enums import Resampling
import numpy as np
import matplotlib.pyplot as plt
import os

def preview_insar_tiff(input_path, max_preview_size=1024):
    """
    快速预览大型 InSAR TIFF 文件（通过降采样读取，避免内存溢出）
    
    :param input_path: 输入的 TIFF 文件路径
    :param max_preview_size: 预览图的最大长/宽像素数
    """
    print(f"正在生成预览: {input_path}")
    
    with rasterio.open(input_path) as src:
        # 计算降采样比例，确保长边不超过 max_preview_size
        scale = min(max_preview_size / src.width, max_preview_size / src.height)
        
        # 如果图像本来就很小，就不需要缩放
        if scale >= 1:
            scale = 1.0
            
        out_shape = (
            src.count,
            int(src.height * scale),
            int(src.width * scale)
        )
        
        print(f"原始尺寸: {src.width}x{src.height}, 预览尺寸: {out_shape[2]}x{out_shape[1]}")
        
        # 读取降采样数据 (使用双线性插值获得更好的视觉效果)
        preview_data = src.read(
            out_shape=out_shape,
            resampling=Resampling.bilinear
        )
        
        # 提取第一个波段进行展示 (InSAR 通常是单波段强度或相位，或者复数)
        band1 = preview_data[0]
        
        # 处理可能存在的复数数据 (Complex)
        if np.iscomplexobj(band1):
            print("检测到复数数据，正在计算振幅(Amplitude)用于预览...")
            band1 = np.abs(band1)
            
        # 忽略 NoData 值和 NaN
        valid_mask = ~np.isnan(band1)
        if src.nodata is not None:
            valid_mask &= (band1 != src.nodata)
            
        valid_data = band1[valid_mask]
        
        # InSAR 数据动态范围极大，进行 2% - 98% 的百分比截断增强对比度
        if len(valid_data) > 0:
            vmin, vmax = np.percentile(valid_data, (2, 98))
            band1_clipped = np.clip(band1, vmin, vmax)
            # 将 nodata 区域设为背景色（如 np.nan 会在 matplotlib 中默认透明/白色）
            band1_clipped[~valid_mask] = np.nan
        else:
            band1_clipped = band1

        # 绘图
        plt.figure(figsize=(10, 8))
        # 灰度图适合看强度，如果是相位数据可以改用 cmap='jet' 或 'hsv'
        plt.imshow(band1_clipped, cmap='gray') 
        plt.colorbar(label='Amplitude / Intensity')
        plt.title(f'InSAR Data Preview\n{os.path.basename(input_path)}')
        plt.tight_layout()
        plt.show()


def compress_and_export_large_tiff(input_path, output_path, quality=85):
    """
    分块读取并压缩导出大型 TIFF 文件为 JPEG 格式
    注意：JPEG 仅支持 1 波段或 3 波段的 8-bit (uint8) 数据
    
    :param input_path: 输入文件路径
    :param output_path: 输出的 JPEG 文件路径
    :param quality: JPEG 压缩质量 (1-100)，默认 85
    """
    print(f"开始压缩并导出为 JPEG...\n输入: {input_path}\n输出: {output_path}")
    
    with rasterio.open(input_path) as src:
        # 获取源影像的元数据
        profile = src.profile
        
        # JPEG 需要修改为 JPEG 驱动，并设置压缩质量
        profile.update(
            driver='JPEG',
            tiled=False,  # JPEG 驱动不支持常规的 TIFF block/tiled
            compress=None, # JPEG 驱动由其自身处理压缩，不需要指定 compress 参数
            quality=quality,
            dtype=rasterio.uint8,  # JPEG 仅支持 uint8
            count=1 # 通常单波段导出，多波段视情况而定
        )
        
        # 移除不支持的 bigtiff 选项
        if 'bigtiff' in profile:
            del profile['bigtiff']
        if 'blockxsize' in profile:
            del profile['blockxsize']
        if 'blockysize' in profile:
            del profile['blockysize']

        with rasterio.open(output_path, 'w', **profile) as dst:
            # 对于大型文件，仍然需要分块读取，以避免内存溢出
            windows = list(src.block_windows(1))
            total_blocks = len(windows)
            
            # 由于可能需要将数据转换为 uint8，我们需要找到全局极值或使用百分比截断
            # 这里为了避免遍历两遍文件，我们仅在局部窗口内进行线性拉伸（2%-98%）到 0-255
            # 注意：局部拉伸可能导致块之间出现边界色差。
            # 更精确的做法是：先降采样读取全局数据，找到全局的 2% 和 98% 极值，再用这两个极值对每个块进行拉伸。
            
            # 为了更好的效果，我们先计算全局近似的 min/max (使用降采样的思路)
            print("正在计算全局对比度极值...")
            scale = min(1024 / src.width, 1024 / src.height)
            if scale >= 1: scale = 1.0
            out_shape = (1, int(src.height * scale), int(src.width * scale))
            preview_data = src.read(out_shape=out_shape, resampling=Resampling.bilinear)[0]
            if np.iscomplexobj(preview_data):
                preview_data = np.abs(preview_data)
            valid_mask = ~np.isnan(preview_data)
            if src.nodata is not None:
                valid_mask &= (preview_data != src.nodata)
            valid_data = preview_data[valid_mask]
            
            if len(valid_data) > 0:
                global_vmin, global_vmax = np.percentile(valid_data, (2, 98))
            else:
                global_vmin, global_vmax = 0, 1

            print(f"全局极值计算完成: vmin={global_vmin:.4f}, vmax={global_vmax:.4f}")

            for i, (ji, window) in enumerate(windows):
                # 仅读取当前窗口的数据 (第一个波段)
                data = src.read(1, window=window)
                
                if np.iscomplexobj(data):
                    data = np.abs(data)
                
                # 处理 NaN 和 NoData
                valid_mask_chunk = ~np.isnan(data)
                if src.nodata is not None:
                    valid_mask_chunk &= (data != src.nodata)

                # 将数据线性拉伸到 0-255 并转换为 uint8
                # 超出 vmin/vmax 的截断
                data_clipped = np.clip(data, global_vmin, global_vmax)
                # 归一化到 0-1
                range_val = global_vmax - global_vmin
                if range_val == 0:
                    range_val = 1
                data_norm = (data_clipped - global_vmin) / range_val
                # 缩放到 0-255
                data_uint8 = (data_norm * 255).astype(rasterio.uint8)
                
                # 将无效区域设为 0 (黑色)
                data_uint8[~valid_mask_chunk] = 0
                
                # 将数据写入到新文件的对应窗口
                dst.write(data_uint8, 1, window=window)
                
                # 打印简单的进度条
                if (i + 1) % max(1, (total_blocks // 10)) == 0 or i == total_blocks - 1:
                    print(f"进度: {((i + 1) / total_blocks) * 100:.1f}%")
                    
    print("导出完成！")

# ================= 使用示例 =================
if __name__ == "__main__":
    # 请替换为你的实际文件路径
    input_file = r"E:\SAR\样本数据\迭戈加西亚_AS08_WH_JS_002276_W18.2_N0.0_20250429094128_L2_HH_02_001\AS08_WH_JS_002276_W18.2_N0.0_20250429094128_L2_HH_02_001.tiff"
    output_file = r"E:\SAR\AS08_WH_JS_002276_W18.2_N0.0_20250429094128_L2_HH_02_001.jpg"
    
    if os.path.exists(input_file):
        # 1. 预览大型 TIFF
        preview_insar_tiff(input_file)
        
        # 2. 压缩导出为 JPEG (质量默认 85)
        compress_and_export_large_tiff(input_file, output_file, quality=85)
    else:
        print("未找到输入文件，请修改 input_file 路径。")