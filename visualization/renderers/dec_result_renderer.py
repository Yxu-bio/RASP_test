from visualization.renderers.diva_result_renderer import DivaResultRenderer


class DECResultRenderer(DivaResultRenderer):
    """
    窄版 DEC renderer。

    当前阶段先复用 DivaResultRenderer 的树显示、点击、高亮、导出链。
    前提是 DECResult / DECNodeResult 已提供与现有绘图链兼容的最小字段：
    - node_results
    - state_order
    - state_colors
    - pie_labels / pie_percents / pie_colors

    这一版的目标不是做 DEC 专用事件图层，
    而是验证第三方法可以在现有 renderer 插槽中接入。
    """
    pass