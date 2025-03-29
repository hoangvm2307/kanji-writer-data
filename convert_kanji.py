import os
import json
import xml.etree.ElementTree as ET
import re
from svgpathtools import parse_path

def extract_from_kanjivg(svg_file_path):
    """Trích xuất thông tin từ file SVG của KanjiVG"""
    
    # Đọc file SVG dưới dạng văn bản
    with open(svg_file_path, 'r', encoding='utf-8') as f:
        svg_content = f.read()
    
    # Phân tích cú pháp file SVG
    tree = ET.parse(svg_file_path)
    root = tree.getroot()
    
    # Tìm tất cả namespaces được sử dụng
    namespaces = {'svg': 'http://www.w3.org/2000/svg'}
    for key, value in root.attrib.items():
        if key.startswith('{'):
            ns = key[1:].split('}')[0]
            ns_prefix = key.split('}')[1]
            namespaces[ns_prefix] = ns
    
    # Debug: In ra tất cả namespaces tìm thấy
    print(f"File: {os.path.basename(svg_file_path)}")
    print(f"Namespaces: {namespaces}")
    
    result = {
        "strokes": [],
        "medians": [],
        "radStrokes": []
    }
    
    # Tìm tất cả các path bằng cách tìm kiếm trực tiếp trong chuỗi SVG
    path_pattern = r'<path[^>]*d="([^"]*)"[^>]*>'
    paths = re.findall(path_pattern, svg_content)
    
    # Debug: In ra số lượng paths tìm thấy
    print(f"Số lượng path tìm thấy: {len(paths)}")
    
    # Nếu không tìm thấy paths qua regex, thử tìm bằng XML parser
    if len(paths) == 0:
        # Thử tìm tất cả các path bất kể namespace
        paths_elements = root.findall('.//path') + root.findall('.//*[@d]')
        
        # Debug: In ra số lượng paths tìm thấy
        print(f"Số lượng path tìm thấy bằng XML parser: {len(paths_elements)}")
        
        for path in paths_elements:
            d_attr = path.get('d')
            if d_attr:
                paths.append(d_attr)
    
    # Thử tìm stroke elements (nếu có)
    stroke_elements = root.findall('.//stroke') + root.findall('.//*[@type="stroke"]')
    
    # Debug: In ra số lượng stroke elements tìm thấy
    print(f"Số lượng stroke elements tìm thấy: {len(stroke_elements)}")
    
    for i, path_data in enumerate(paths):
        if path_data:
            # Thêm đường dẫn vào danh sách strokes
            result["strokes"].append(path_data)
            
            # Tạo các điểm trung tâm từ đường dẫn SVG
            median_points = extract_median_points(path_data)
            result["medians"].append(median_points)
    
    # Kiểm tra xem có radical information trong thẻ g hay không
    g_elements = root.findall('.//g') + root.findall('.//*[@element]')
    for i, g in enumerate(g_elements):
        element = g.get('element')
        if element and 'rad' in element.lower():
            # Tìm các path trong g element này
            radical_paths = g.findall('.//path') + g.findall('.//*[@d]')
            for path in radical_paths:
                # Tìm index của path trong danh sách paths
                d_attr = path.get('d')
                if d_attr and d_attr in result["strokes"]:
                    index = result["strokes"].index(d_attr)
                    if index not in result["radStrokes"]:
                        result["radStrokes"].append(index)
    
    # Nếu vẫn không tìm thấy radical strokes, thử tìm theo thuộc tính type
    if len(result["radStrokes"]) == 0:
        for ns_prefix, ns in namespaces.items():
            for i, path in enumerate(root.findall('.//*[@{%s}type]' % ns)):
                stroke_type = path.get('{%s}type' % ns)
                if stroke_type and 'radical' in stroke_type.lower():
                    d_attr = path.get('d')
                    if d_attr and d_attr in result["strokes"]:
                        index = result["strokes"].index(d_attr)
                        if index not in result["radStrokes"]:
                            result["radStrokes"].append(index)
    
    # Debug: In ra số lượng strokes và radStrokes
    print(f"Số lượng strokes: {len(result['strokes'])}")
    print(f"Số lượng radStrokes: {len(result['radStrokes'])}")
    
    return result

def extract_median_points(path_data):
    """Trích xuất các điểm trung tâm từ đường dẫn SVG"""
    
    try:
        # Phân tích đường dẫn SVG
        path = parse_path(path_data)
        
        # Không đủ dữ liệu để xử lý
        if len(path) == 0:
            return [[0, 0], [0, 0]]  # Trả về giá trị mặc định
        
        median_points = []
        
        # Chia mỗi phần tử đường dẫn thành nhiều điểm
        num_points = max(2, min(10, len(path) * 2))  # Ít nhất 2 điểm, nhiều nhất 10
        
        for i in range(num_points):
            t = i / (num_points - 1)
            point = path.point(t)
            median_points.append([int(point.real), int(point.imag)])
        
        # Đảm bảo có ít nhất 2 điểm
        if len(median_points) < 2:
            median_points.append(median_points[0])
            
        return median_points
        
    except Exception as e:
        print(f"Lỗi khi xử lý đường dẫn SVG: {e}")
        # Trả về giá trị mặc định nếu có lỗi
        return [[0, 0], [1, 1]]

def convert_kanji_with_variants():
    """Chuyển đổi file SVG dựa theo file index, xử lý cả biến thể Kaisho"""
    
    # Thư mục chứa file SVG
    input_dir = "kanji"
    
    # Thư mục đầu ra cho file JSON
    output_dir = "output"
    
    # Tạo thư mục đầu ra nếu chưa tồn tại
    os.makedirs(output_dir, exist_ok=True)
    
    # Đọc file index
    try:
        with open("kvg-index.json", "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception as e:
        print(f"Lỗi khi đọc file index: {e}")
        return
    
    count_standard = 0
    count_kaisho = 0
    error_count = 0
    
    # Chọn một mẫu nhỏ để kiểm tra (10 ký tự đầu tiên)
    sample_keys = list(index.keys())[:10]
    
    for kanji in sample_keys:
        svg_files = index[kanji]
        # Phân loại các file SVG
        standard_svg = None
        kaisho_svg = None
        
        for svg in svg_files:
            if "-Kaisho" in svg:
                kaisho_svg = svg
            else:
                standard_svg = svg
        
        # Xử lý phiên bản tiêu chuẩn
        if standard_svg:
            svg_path = os.path.join(input_dir, standard_svg)
            if os.path.exists(svg_path):
                try:
                    # Trích xuất dữ liệu từ file SVG
                    data = extract_from_kanjivg(svg_path)
                    
                    # Kiểm tra xem có dữ liệu không
                    if len(data["strokes"]) == 0:
                        print(f"CẢNH BÁO: Không tìm thấy strokes cho {kanji} ({svg_path})")
                        error_count += 1
                        continue
                    
                    # Tạo tên file đầu ra dựa trên ký tự Kanji
                    output_file = os.path.join(output_dir, f"{kanji}.json")
                    
                    # Lưu dữ liệu vào file JSON
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    count_standard += 1
                    print(f"Đã chuyển đổi {kanji} (tiêu chuẩn)")
                    
                except Exception as e:
                    print(f"Lỗi khi chuyển đổi {kanji} (tiêu chuẩn - {svg_path}): {e}")
                    error_count += 1
    
    print(f"\nKết quả kiểm tra mẫu 10 ký tự đầu tiên:")
    print(f"- Thành công: {count_standard + count_kaisho}")
    print(f"- Lỗi: {error_count}")
    
    # Hỏi người dùng có muốn tiếp tục chuyển đổi tất cả không
    response = input("\nBạn có muốn tiếp tục chuyển đổi tất cả các ký tự không? (y/n): ")
    
    if response.lower() != 'y':
        print("Đã hủy quá trình chuyển đổi.")
        return
    
    # Reset bộ đếm
    count_standard = 0
    count_kaisho = 0
    error_count = 0
    
    # Chuyển đổi tất cả các ký tự
    for kanji, svg_files in index.items():
        # Phân loại các file SVG
        standard_svg = None
        kaisho_svg = None
        
        for svg in svg_files:
            if "-Kaisho" in svg:
                kaisho_svg = svg
            else:
                standard_svg = svg
        
        # Xử lý phiên bản tiêu chuẩn
        if standard_svg:
            svg_path = os.path.join(input_dir, standard_svg)
            if os.path.exists(svg_path):
                try:
                    # Trích xuất dữ liệu từ file SVG
                    data = extract_from_kanjivg(svg_path)
                    
                    # Kiểm tra xem có dữ liệu không
                    if len(data["strokes"]) == 0:
                        continue
                    
                    # Tạo tên file đầu ra dựa trên ký tự Kanji
                    output_file = os.path.join(output_dir, f"{kanji}.json")
                    
                    # Lưu dữ liệu vào file JSON
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    count_standard += 1
                    
                    if count_standard % 100 == 0:
                        print(f"Đã chuyển đổi {count_standard} file tiêu chuẩn...")
                    
                except Exception as e:
                    error_count += 1
        
        # Xử lý phiên bản Kaisho nếu có
        if kaisho_svg:
            svg_path = os.path.join(input_dir, kaisho_svg)
            if os.path.exists(svg_path):
                try:
                    # Trích xuất dữ liệu từ file SVG
                    data = extract_from_kanjivg(svg_path)
                    
                    # Kiểm tra xem có dữ liệu không
                    if len(data["strokes"]) == 0:
                        continue
                    
                    # Tạo tên file đầu ra dựa trên ký tự Kanji, thêm hậu tố -Kaisho
                    output_file = os.path.join(output_dir, f"{kanji}-Kaisho.json")
                    
                    # Lưu dữ liệu vào file JSON
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    count_kaisho += 1
                    
                    if count_kaisho % 100 == 0:
                        print(f"Đã chuyển đổi {count_kaisho} file Kaisho...")
                    
                except Exception as e:
                    error_count += 1
    
    total = count_standard + count_kaisho
    print(f"Đã hoàn thành! Chuyển đổi tổng cộng {total} file ({count_standard} tiêu chuẩn, {count_kaisho} Kaisho).")
    print(f"Số lượng lỗi: {error_count}")

# Chạy chương trình
if __name__ == "__main__":
    convert_kanji_with_variants()