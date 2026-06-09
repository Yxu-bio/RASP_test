from visualization.renderers.dec_result_renderer import DECResultRenderer


class SDECResultRenderer(DECResultRenderer):
    """
    S-DEC 第一版直接复用 DEC renderer。
    当前差异只在结果语义层，不在树图绘制层。
    """
    pass
