# utils/safety_stock/help.py
"""
User Guide Popover for Safety Stock Management.
Renders a self-contained ❓ help button with 7-tab documentation.

Tabs:
  📌 Overview | 📚 Concepts | 🔧 How To | 📐 Methods | 📊 Analysis | 👥 Roles | ❓ FAQ

Usage:
    from utils.safety_stock.help import render_help_popover
    render_help_popover()
"""

import streamlit as st


def render_help_popover():
    """Help & User Guide popover — accessible from the page header"""
    with st.popover("❓ User Guide"):
        st.markdown("## 🛡️ Safety Stock Management — User Guide")

        tab_overview, tab_concepts, tab_howto, tab_methods, tab_analysis, tab_roles, tab_faq = st.tabs([
            "📌 Overview", "📚 Concepts", "🔧 How To", "📐 Methods", "📊 Analysis", "👥 Roles", "❓ FAQ"
        ])

        # ══════════════════════════════════════════════════════════════════════
        # TAB 1 — Overview
        # ══════════════════════════════════════════════════════════════════════
        with tab_overview:
            st.markdown("""
**Safety Stock Management** cho phép bạn thiết lập và quản lý mức tồn kho đệm (buffer stock)
cho từng sản phẩm, đảm bảo không bị stockout khi có biến động về cung hoặc cầu.

---

### Luồng sử dụng cơ bản
1. 🔍 **Xem** danh sách rules qua bảng dữ liệu — lọc theo entity, customer, product, status
2. ➕ **Tạo mới** rule bằng nút *Add Safety Stock*
3. ✏️ **Chỉnh sửa** bằng cách chọn dòng → click *Edit*
4. 📋 **Review** định kỳ để cập nhật số lượng và ghi lý do thay đổi
5. 📊 **Compare** tồn kho thực tế vs SS target theo warehouse
6. 📈 **Analysis** để deep-dive lịch sử biến động, coverage và rule health

---

### KPI Dashboard (8 metrics — đầu trang)
| Metric | Ý nghĩa |
|---|---|
| Active Rules | Tổng số rule đang hiệu lực |
| Customer Rules | Rule áp dụng riêng cho 1 khách hàng cụ thể |
| Needs Review | Rule chưa được recalculate trong 30 ngày |
| Unique Products | Số sản phẩm có ít nhất 1 rule active |
| Expiring in 30d | Rule có `effective_to` trong vòng 30 ngày tới |
| No Reorder Point | Rule chưa có ROP — cần bổ sung |
| Manual (FIXED) % | Tỷ lệ rule dùng nhập tay, kèm gợi ý migrate sang DOS/LTB |
| Auto-Calculated % | Tỷ lệ rule dùng DOS hoặc LTB |

---

### Các sections trên trang
| Section | Vị trí | Mục đích |
|---|---|---|
| KPI Stats | Đầu trang | Tổng quan nhanh |
| Filters | Bên dưới stats | Lọc dữ liệu |
| Data Table | Chính giữa | Xem và thao tác rules |
| Actions Panel | Bên dưới table | Edit / Review / Compare / Delete |
| Analysis | Cuối trang | Analytics & reporting |
""")

        # ══════════════════════════════════════════════════════════════════════
        # TAB 2 — Concepts
        # ══════════════════════════════════════════════════════════════════════
        with tab_concepts:
            st.markdown("""
### Safety Stock (SS)
Lượng tồn kho đệm dự phòng, giữ trên mức zero để chống lại sự biến động của cầu và thời gian
giao hàng. SS cao hơn = ít stockout hơn nhưng chi phí lưu kho cao hơn.

---

### Reorder Point (ROP)
Ngưỡng tồn kho kích hoạt lệnh mua hàng mới.

```
ROP = (Lead Time × Avg Daily Demand) + Safety Stock
```

Khi tồn kho thực tế **chạm ROP**, cần đặt hàng ngay để hàng về đúng lúc tồn kho hết.

---

### Coverage %
```
Coverage % = On Hand ÷ SS Target × 100
```
- **≥ 100%** — Tồn kho đủ, an toàn
- **< 100%** — Tồn kho dưới mức safety buffer
- **≤ ROP** — Cần đặt hàng ngay (Below ROP)

---

### General Rule vs Customer-Specific Rule
| | General Rule | Customer-Specific |
|---|---|---|
| Customer field | All | Một khách hàng cụ thể |
| Phạm vi | Tất cả khách | Chỉ khách đó |
| Priority | Cao hơn (số lớn hơn) | Thấp hơn (số nhỏ hơn) |
| Use case | Baseline buffer | Override đặc biệt |

> Rule có **Priority Level thấp hơn** được ưu tiên (VD: priority 1 > priority 100)

---

### Effective Period
- `effective_to = ongoing` — rule không có ngày hết hạn
- Khi tạo rule mới thay thế rule cũ, nên set `effective_to` cho rule cũ để tránh conflict
- Rules **sắp hết hạn trong 30 ngày** sẽ hiển thị cảnh báo màu vàng đầu trang

---

### Calculation Methods (tóm tắt)
| Method | Tên đầy đủ | Khi nào dùng |
|---|---|---|
| FIXED | Manual | Ít data, có kinh nghiệm thực tế |
| DOS | Days of Supply | Demand ổn định (CV% < 20%) |
| LTB | Lead Time Based | Demand biến động (CV% ≥ 20%, ≥ 30 data points) |

---

### Review vs Edit
| | Review | Edit |
|---|---|---|
| Mục đích | Cập nhật số lượng + ghi lý do | Thay đổi mọi thông tin |
| Audit trail | ✅ Tự động | ❌ Không có riêng |
| Method change | ❌ Không được | ✅ Được |
| Use case | Điều chỉnh định kỳ | Thay đổi cấu hình |
""")

        # ══════════════════════════════════════════════════════════════════════
        # TAB 3 — How To
        # ══════════════════════════════════════════════════════════════════════
        with tab_howto:

            st.markdown("### 🔍 Sử dụng Filters")
            st.markdown("""
**Row 1 — Filters chính:**
| Filter | Mô tả |
|---|---|
| Entity | Lọc theo công ty bán hàng |
| Customer | All / General Rules Only / khách hàng cụ thể |
| Product Search | Tìm theo PT code hoặc tên sản phẩm (gõ để search) |
| Status | Active / All / Expired / Future |

**Row 2 — Advanced filters:**
| Filter | Mô tả |
|---|---|
| Calculation Method | Lọc theo FIXED / DOS / LTB |
| ⚠️ Needs Review Only | Rules chưa recalculate trong 30 ngày |
| 📅 Expiring in 30 Days | Rules sắp hết hiệu lực |
| 🔴 No Reorder Point | Rules chưa có ROP |
| 📋 Has Reviews | Rules đã từng được review ít nhất 1 lần |

> 💡 Khi filter **Expiring in 30 Days** đang tắt mà có rules sắp hết hạn,
> banner cảnh báo màu vàng sẽ tự động hiện trên đầu bảng.
""")
            st.divider()

            st.markdown("### 📋 Đọc bảng dữ liệu")
            st.markdown("""
**Columns trong bảng:**
| Column | Mô tả |
|---|---|
| PT Code | Mã sản phẩm |
| Product Name | Tên sản phẩm đầy đủ |
| Brand | Thương hiệu |
| Entity | Mã công ty |
| Customer | Mã khách hàng, hoặc `All` cho General Rule |
| SS Qty | Safety stock quantity hiện tại |
| Reorder Point | Ngưỡng đặt hàng (`—` = chưa set) |
| Method | FIXED / DOS / LTB |
| Rule Type | Customer Specific / General Rule |
| Status | Active / Expired / Future / Inactive |
| Effective Period | `2025-11-01 → ongoing` hoặc có ngày kết thúc |
| Priority | Số nhỏ = ưu tiên cao hơn |
| Last Calculated | Ngày tính toán gần nhất |
| Reviews | Badge icon + số lần review (VD: `📈 3`) |
| Last Review | Ngày review gần nhất |

**Màu sắc dòng** (phản ánh lần review gần nhất):
| Màu | Ý nghĩa |
|---|---|
| 🟢 Xanh lá | SS tăng (INCREASED) |
| 🟠 Amber | SS giảm (DECREASED) |
| 🔵 Xanh dương | Method thay đổi (METHOD_CHANGED) |
| 🟣 Tím | Đã review, không đổi số lượng (NO_CHANGE) |
| ⬜ Trắng | Chưa từng review |
""")
            st.divider()

            st.markdown("### ➕ Tạo Safety Stock Rule mới")
            st.markdown("""
1. Click **➕ Add Safety Stock**
2. **Tab 1 — Basic Information:**
   - Chọn **Product** (gõ PT code hoặc tên để search)
   - Chọn **Entity** (công ty bán hàng)
   - Chọn **Customer** nếu là rule riêng — để trống cho General Rule
   - Đặt **Priority Level**: Customer rules nên ≤ 500, General rules mặc định 100
   - Đặt **Effective From** (ngày bắt đầu) và **Effective To** (để trống = không hết hạn)
3. **Tab 2 — Stock Levels & Calculation:**
   - Click **Fetch Data** để lấy lịch sử demand (mặc định 180 ngày)
   - Xem CV% để đánh giá độ biến động
   - Hệ thống tự gợi ý method phù hợp
   - Chọn method, điền parameters và click **Calculate**
   - Kiểm tra **SS**, **ROP** và **Formula** ở Summary
4. Click **💾 Save**

> ⚠️ Method trong dropdown phải khớp với method đã Calculate. Nếu không khớp, hệ thống sẽ block Save.
""")
            st.divider()

            st.markdown("### ✏️ Chỉnh sửa Rule")
            st.markdown("""
1. Click vào dòng cần sửa trong bảng → hiện **Actions panel** bên dưới
2. Click **✏️ Edit**
3. Chỉnh sửa thông tin mong muốn
4. Nếu đổi Calculation Method → bắt buộc bấm **Calculate** lại
5. Click **💾 Save**

> ⚠️ Edit không tạo audit trail riêng. Dùng **Review** nếu chỉ muốn điều chỉnh số lượng và ghi lý do.
""")
            st.divider()

            st.markdown("### 📋 Review Rule")
            st.markdown("""
Review ghi nhận sự thay đổi số lượng SS và tạo **audit trail đầy đủ**.

1. Chọn dòng → click **📋 Review**
2. Điều chỉnh **New Safety Stock Quantity**
   - Badge tự động: `INCREASED` / `DECREASED` / `NO_CHANGE` + % thay đổi
3. Chọn **Review Type**:
   - `PERIODIC` — Review định kỳ (hàng tuần/tháng)
   - `EXCEPTION` — Xử lý bất thường (stockout, surge demand)
   - `EMERGENCY` — Khẩn cấp
   - `ANNUAL` — Review năm
4. Điền **Reason** (bắt buộc, tối thiểu 10 ký tự)
5. Click **Submit** → SS cập nhật và row chuyển màu tương ứng

> ⚠️ Nếu cần thay đổi Calculation Method, dùng **Edit** thay vì Review.
""")
            st.divider()

            st.markdown("### 📊 Compare vs Inventory")
            st.markdown("""
So sánh tồn kho thực tế với SS target cho sản phẩm đang chọn.

1. Chọn dòng → click **📊 Compare vs Inventory**
2. Panel mở bên dưới, hiển thị:
   - **SS Target** — Mức safety stock đang set
   - **Total On Hand** — Tổng tồn kho thực tế (delta màu xanh/đỏ so với SS)
   - **Reorder Point** — Ngưỡng đặt hàng
   - **ROP Status** — `Above ROP` (an toàn) / `Below ROP` (cần đặt hàng)
   - Breakdown tồn kho theo từng **warehouse**
3. Click **✕ Close** để đóng panel
""")
            st.divider()

            st.markdown("### 🗑️ Xóa Rule")
            st.markdown("""
1. Chọn dòng → Actions panel hiện bên dưới
2. Click **🗑️ Delete** → confirm dialog với tên sản phẩm
3. Click **Yes, Delete** để xác nhận hoặc **No, Cancel** để hủy

> ⚠️ Chỉ Admin / MD / GM có quyền xóa. Xóa không thể hoàn tác.
""")
            st.divider()

            st.markdown("### 📤 Bulk Upload")
            st.markdown("""
Import nhiều rules cùng lúc từ file Excel.

1. Click **📤 Bulk Upload**
2. Click **Download Template** để tải file mẫu đúng format
3. Điền dữ liệu → upload file → xem preview 10 dòng đầu
4. Click **Import** để hoàn tất

**Cột bắt buộc:** `product_id`, `entity_id`, `safety_stock_qty`, `effective_from`

**Cột tùy chọn:** `customer_id`, `reorder_point`, `calculation_method`,
`priority_level`, `effective_to`, `business_notes`
""")

        # ══════════════════════════════════════════════════════════════════════
        # TAB 4 — Methods
        # ══════════════════════════════════════════════════════════════════════
        with tab_methods:
            st.markdown("### 📐 Chi tiết các Calculation Methods")

            st.markdown("#### 1️⃣ FIXED — Nhập tay")
            st.info("Dùng khi: không có đủ data lịch sử, hoặc đã có kinh nghiệm thực tế về mức buffer cần thiết.")
            st.code("SS  = [Nhập tay]\nROP = [Nhập tay hoặc để trống]", language="text")
            st.markdown("""
- Không cần Fetch Data
- Phù hợp: sản phẩm mới, sản phẩm theo mùa, thỏa thuận tồn kho với khách
""")

            st.divider()
            st.markdown("#### 2️⃣ DOS — Days of Supply")
            st.info("Dùng khi: demand tương đối ổn định (CV% < 20%). Phương pháp đơn giản, dễ giải thích.")
            st.code(
                "SS  = Safety Days × Avg Daily Demand\n"
                "ROP = (Lead Time Days × Avg Daily Demand) + SS",
                language="text"
            )
            st.markdown("""
| Parameter | Nguồn | Mô tả |
|---|---|---|
| Safety Days | Nhập tay | Số ngày buffer (VD: 14 ngày) |
| Avg Daily Demand | Auto-fetch | Demand trung bình mỗi ngày |
| Lead Time (days) | Nhập tay | Thời gian từ đặt đến nhận hàng |

> Gợi ý Safety Days: thông thường 7–30 ngày tùy loại hàng.
""")

            st.divider()
            st.markdown("#### 3️⃣ LTB — Lead Time Based (Statistical)")
            st.info("Dùng khi: demand biến động cao (CV% ≥ 20%) và có đủ ≥ 30 data points. Chính xác nhất.")
            st.code(
                "SS  = Z × √(Lead Time) × σ_daily_demand\n"
                "ROP = (Lead Time Days × Avg Daily Demand) + SS",
                language="text"
            )
            st.markdown("""
| Parameter | Nguồn | Mô tả |
|---|---|---|
| Z-score | Tính từ service level % | Hệ số độ tin cậy |
| Lead Time (days) | Nhập tay | Thời gian giao hàng |
| σ_daily_demand | Auto-fetch | Std deviation của demand hàng ngày |
| Avg Daily Demand | Auto-fetch | Demand trung bình hàng ngày |

**Service Level Reference:**
| Service Level | Z-score | Ý nghĩa thực tế |
|---|---|---|
| 90% | 1.28 | Chấp nhận stockout ~10% thời gian |
| 95% | 1.65 | Cân bằng tốt — thông dụng nhất |
| 97% | 1.88 | An toàn hơn |
| 99% | 2.33 | Rất an toàn, tồn kho cao hơn đáng kể |
| 99.9% | 3.09 | Cực kỳ an toàn — chi phí lưu kho rất cao |
""")

            st.divider()
            st.markdown("#### 🤖 Auto-suggest Logic")
            st.markdown("""
| Điều kiện | Gợi ý | Lý do |
|---|---|---|
| < 10 data points | FIXED | Không đủ data |
| ≥ 10 points, CV% < 20% | DOS | Demand ổn định |
| ≥ 30 points, CV% ≥ 20% | LTB | Đủ data + demand biến động |
| 10–29 points, CV% ≥ 20% | DOS | Chưa đủ data cho LTB |
""")

        # ══════════════════════════════════════════════════════════════════════
        # TAB 5 — Analysis Section
        # ══════════════════════════════════════════════════════════════════════
        with tab_analysis:
            st.markdown("""
**Analysis Section** nằm ở **cuối trang**, cho phép deep-dive vào lịch sử review,
xu hướng SS, coverage tồn kho và chất lượng rules.

**Shared Controls** (áp dụng cho tất cả tabs):
- **Entity filter** — lọc theo công ty
- **History window** — khoảng thời gian phân tích (30 ngày → 1 năm)
""")
            st.divider()

            st.markdown("### 📋 Tab: Review History")
            st.markdown("""
Hiển thị **toàn bộ review events** trong khoảng thời gian được chọn.

**4 KPI metrics:** Total Reviews · Products Reviewed · 📈 Increased · 📉 Decreased

**Bar chart:** events theo ngày, phân màu theo action type:
- 🟢 INCREASED · 🟠 DECREASED · ⚪ NO_CHANGE · 🔵 METHOD_CHANGED

**Filter by action:** lọc bảng theo loại action

**Detail table:** date, PT Code, Product, old SS → new SS, change %, action, reason, reviewer
""")
            st.divider()

            st.markdown("### 📈 Tab: SS Trend")
            st.markdown("""
Theo dõi **SS quantity thay đổi qua thời gian** cho 1 sản phẩm cụ thể.

1. Chọn Product từ dropdown (chỉ hiện sản phẩm có lịch sử review)
2. Xem **line chart**: mỗi điểm = 1 lần review, màu = action type
3. Hover để xem: ngày, old SS, new SS, % thay đổi

**3 metrics:** số reviews · Starting SS · Current SS (+ delta % so với ban đầu)
""")
            st.divider()

            st.markdown("### ⚖️ Tab: Coverage Analysis")
            st.markdown("""
So sánh **on-hand inventory vs SS target** — xác định sản phẩm có rủi ro stockout.

**4 status categories:**
| Status | Màu | Ý nghĩa |
|---|---|---|
| Below ROP 🔴 | Đỏ | Tồn kho ≤ ROP → cần đặt hàng ngay |
| Below SS 🟠 | Cam | Tồn kho < SS Target nhưng > ROP |
| Above SS 🟢 | Xanh | Tồn kho ≥ SS Target → an toàn |
| No Data ⚪ | Xám | Không có dữ liệu tồn kho |

**Bar chart:** top 40 sản phẩm có coverage thấp nhất + đường đỏ đứt tại 100%

**Filter + full table** phía dưới chart
""")
            st.divider()

            st.markdown("### 🔍 Tab: Rule Health")
            st.markdown("""
**Scorecard chất lượng** toàn bộ active rules.

**5 KPI:**
| Metric | Lý tưởng |
|---|---|
| Active Rules | — |
| Never Reviewed | = 0 |
| Missing ROP | = 0 |
| Manual (FIXED) % | < 50% |
| Stale >60d | = 0 |

**Donut chart:** phân bổ FIXED / DOS / LTB

**Drill-down tabs:**
- 🕰️ **Never Reviewed** — danh sách rules chưa có review nào
- ❓ **Missing ROP** — danh sách rules chưa set Reorder Point
- 📋 **Stale >60d** — danh sách rules quá 60 ngày chưa recalculate
""")

        # ══════════════════════════════════════════════════════════════════════
        # TAB 6 — Roles
        # ══════════════════════════════════════════════════════════════════════
        with tab_roles:
            st.markdown("### 👥 Phân quyền theo Role")
            st.markdown("""
| Role | Xem | Tạo | Sửa | Xóa | Review | Bulk | Export | Analysis |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Admin / MD / GM | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Supply Chain | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Sales Manager | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ |
| Sales | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ |
| Viewer | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| Customer | ✅* | ❌ | ❌ | ❌ | ❌ | ❌ | ✅* | ❌ |

> *Customer chỉ xem và export data của chính họ.

**Export limits theo role:**
| Role | Giới hạn dòng |
|---|---|
| Customer | 1,000 dòng |
| Sales / Viewer | 5,000 dòng |
| Sales Manager | 10,000 dòng |
| Supply Chain / Admin / MD / GM | Không giới hạn |

**Lưu ý:**
- **Sales** có thể Review nhưng không tạo/sửa rule — phù hợp confirm tình trạng tồn kho
- **Bulk Upload** chỉ Supply Chain trở lên để tránh import lỗi quy mô lớn
- **Xóa** chỉ Admin / MD / GM vì không thể hoàn tác
""")

        # ══════════════════════════════════════════════════════════════════════
        # TAB 7 — FAQ
        # ══════════════════════════════════════════════════════════════════════
        with tab_faq:
            st.markdown("### ❓ Câu hỏi thường gặp")

            with st.expander("Màu sắc dòng trong bảng có ý nghĩa gì?"):
                st.markdown("""
Màu phản ánh **kết quả lần review gần nhất** của rule đó:
- 🟢 **Xanh lá** — SS đã tăng (INCREASED)
- 🟠 **Amber** — SS đã giảm (DECREASED)
- 🔵 **Xanh dương** — Method đã thay đổi (METHOD_CHANGED)
- 🟣 **Tím** — Đã review, không đổi số lượng (NO_CHANGE)
- ⬜ **Trắng** — Chưa từng review

Dùng filter **📋 Has Reviews** để chỉ xem rules có lịch sử review.
""")

            with st.expander("Filter 'Has Reviews' khác gì 'Needs Review Only'?"):
                st.markdown("""
| Filter | Điều kiện | Ý nghĩa |
|---|---|---|
| 📋 **Has Reviews** | `review_count > 0` | Rules đã có ít nhất 1 review event |
| ⚠️ **Needs Review Only** | `last_calculated_date < 30 ngày trước` | Rules chưa recalculate gần đây |

Hai filter độc lập và có thể kết hợp:
- Rule đã review nhiều lần nhưng chưa recalculate → xuất hiện ở cả hai
- Rule mới chưa review → chỉ ở Needs Review Only
""")

            with st.expander("Tại sao Reorder Point hiển thị '—'?"):
                st.markdown("""
Rule đó chưa được set ROP:
- **FIXED**: cần nhập thủ công trong Edit
- **DOS / LTB**: được tính tự động khi bấm **Calculate** — nếu chưa Calculate thì chưa có

Dùng filter **🔴 No Reorder Point** để xem danh sách và bổ sung.
""")

            with st.expander("Tại sao thấy cảnh báo 'Method mismatch' khi Save?"):
                st.markdown("""
Bạn đã đổi dropdown method nhưng chưa bấm **Calculate** lại.
Kết quả SS/ROP hiển thị vẫn là của method cũ — hệ thống block Save để tránh lưu dữ liệu sai.

**Cách fix:** chọn đúng method → bấm **Calculate** → kết quả cập nhật → **Save**.
""")

            with st.expander("Fetch Data lấy dữ liệu từ đâu?"):
                st.markdown("""
- **Nguồn**: `stock_out_delivery` + `stock_out_delivery_request_details`
- **Group theo**: `COALESCE(adjust_etd_date, etd_date)` — ETD có điều chỉnh được ưu tiên
- **Loại trừ**: status `PENDING`
- **Khoảng thời gian**: mặc định 180 ngày, điều chỉnh 30–365 ngày
- **Kết quả**: avg daily demand, std deviation, số data points, CV%, gợi ý method
""")

            with st.expander("CV% là gì và ảnh hưởng thế nào đến method?"):
                st.markdown("""
```
CV% = (Std Dev ÷ Avg Daily Demand) × 100
```
Đo mức độ biến động tương đối của demand:

| CV% | Biến động | Gợi ý | Ghi chú |
|---|---|---|---|
| < 20% | Thấp 🟢 | DOS | Demand đều đặn |
| 20–50% | Vừa 🟡 | LTB | Cần buffer thống kê |
| > 50% | Cao 🔴 | LTB + service level cao | Demand rất bất thường |
""")

            with st.expander("Coverage Analysis trong Analysis section hoạt động thế nào?"):
                st.markdown("""
So sánh on-hand inventory vs SS target cho tất cả active rules.

- **Dữ liệu tồn kho**: bảng `inventory_histories`, sum `remain` theo `product_id`
- **Coverage %** = On Hand ÷ SS Target × 100
- **Chart**: top 40 sản phẩm coverage thấp nhất, đường đỏ đứt tại 100%
- **Priority xem xét**: Below ROP 🔴 → Below SS 🟠 → Above SS 🟢
""")

            with st.expander("Rule Health Scorecard dùng để làm gì?"):
                st.markdown("""
Đánh giá chất lượng toàn bộ rules và phát hiện vấn đề cần xử lý:

| Issue | Hành động gợi ý |
|---|---|
| Never Reviewed | Lên lịch review định kỳ |
| Missing ROP | Edit → thêm Reorder Point |
| Manual (FIXED) > 50% | Migrate sang DOS/LTB khi có đủ data |
| Stale >60d | Recalculate để cập nhật theo demand mới |
""")

            with st.expander("Expiring in 30 Days — cần làm gì?"):
                st.markdown("""
Rule sắp hết hiệu lực. Nếu không xử lý, sản phẩm sẽ mất safety stock rule active.

**2 lựa chọn:**
1. **Gia hạn**: Edit → cập nhật `effective_to` sang ngày mới hoặc để trống
2. **Thay thế**: Tạo rule mới → set `effective_from` từ ngày rule cũ hết

Dùng filter **📅 Expiring in 30 Days** để xem danh sách đầy đủ.
""")

            with st.expander("Bulk Upload cần file format như thế nào?"):
                st.markdown("""
Download template từ **📤 Bulk Upload → Download Template**.

**Bắt buộc**: `product_id`, `entity_id`, `safety_stock_qty`, `effective_from`

**Tùy chọn**: `customer_id`, `reorder_point`, `calculation_method`,
`priority_level`, `effective_to`, `business_notes`

`calculation_method` chấp nhận: `FIXED` / `DAYS_OF_SUPPLY` / `LEAD_TIME_BASED`
""")