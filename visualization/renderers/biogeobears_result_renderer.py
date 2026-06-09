from visualization.renderers.dec_result_renderer import DECResultRenderer


class BioGeoBEARSResultRenderer(DECResultRenderer):
    """
    第一版直接复用 DEC 的树图渲染风格。
    结果语义区分由 adapter 和 method_name 负责。
    """
    pass