import math
# from copy import copy
from pathlib import Path

import copy
import warnings

import numpy as np
import pandas as pd
import requests
import torch
import torch.nn as nn
from PIL import Image
from torch.cuda import amp
import torch.nn.functional as F

from torch.nn import init, Sequential
from utils.datasets import letterbox
from utils.general import non_max_suppression, make_divisible, scale_coords, increment_path, xyxy2xywh, save_one_box, \
    build_2d_sincos_position_embedding, with_pos_embed
from utils.plots import colors, plot_one_box
from utils.torch_utils import time_synchronized



def autopad(k, p=None):  # kernel, padding
    # Pad to 'same'
    if p is None:
        p = k // 2 if isinstance(k, int) else [x // 2 for x in k]  # auto-pad
    return p


def DWConv(c1, c2, k=1, s=1, act=True):
    # Depthwise convolution
    return Conv(c1, c2, k, s, g=math.gcd(c1, c2), act=act)


class Conv(nn.Module):
    # Standard convolution
    def __init__(self, c1, c2, k=1, s=1, p=None, g=1, act=True):  # ch_in, ch_out, kernel, stride, padding, groups
        super(Conv, self).__init__()
        # print(c1, c2, k, s,)
        self.conv = nn.Conv2d(c1, c2, k, s, autopad(k, p), groups=g, bias=False)
        self.bn = nn.BatchNorm2d(c2)
        self.act = nn.SiLU() if act is True else (act if isinstance(act, nn.Module) else nn.Identity())

    def forward(self, x):
        # print("Conv", x.shape)
        return self.act(self.bn(self.conv(x)))

    def fuseforward(self, x):
        return self.act(self.conv(x))


class TransformerEncoderLayer(nn.Module):
    def __init__(self,
                 d_model,
                 nhead,
                 dim_feedforward=2048,
                 dropout=0.1,
                 # activation="relu",
                 normalize_before=False):
        super().__init__()
        self.normalize_before = normalize_before

        self.self_attn = nn.MultiheadAttention(d_model, nhead, dropout, batch_first=True)

        self.linear1 = nn.Linear(d_model, dim_feedforward)
        self.dropout = nn.Dropout(dropout)
        self.linear2 = nn.Linear(dim_feedforward, d_model)

        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout1 = nn.Dropout(dropout)
        self.dropout2 = nn.Dropout(dropout)
        self.activation = nn.GELU()

    # @staticmethod

    def forward(self, src, src_mask=None, pos_embed=None) -> torch.Tensor:
        residual = src
        if self.normalize_before:
            src = self.norm1(src)

        q = k = with_pos_embed(src, pos_embed.to(src.device))
        # q=k=src
        # del pos_embed
        src, _ = self.self_attn(q, k, value=src, attn_mask=src_mask)

        src = residual + self.dropout1(src)
        if not self.normalize_before:
            src = self.norm1(src)

        residual = src
        if self.normalize_before:
            src = self.norm2(src)
        src = self.linear2(self.dropout(self.activation(self.linear1(src))))
        src = residual + self.dropout2(src)
        if not self.normalize_before:
            src = self.norm2(src)
        return src


class TransformerEncoder(nn.Module):
    def __init__(self, encoder_layer, num_layers, norm=None):
        super(TransformerEncoder, self).__init__()
        self.layers = nn.ModuleList([copy.deepcopy(encoder_layer) for _ in range(num_layers)])
        self.num_layers = num_layers
        self.norm = norm

    def forward(self, src, src_mask=None, pos_embed=None) -> torch.Tensor:
        output = src
        for layer in self.layers:
            output = layer(output, src_mask=src_mask, pos_embed=pos_embed)

        if self.norm is not None:
            output = self.norm(output)
        return output


class Encoder(nn.Module):
    def __init__(self, hidden_dim, num_encoder_layers, use_encoder_idx, nhead=8, dim_feedforward=1024, dropout=0.0):
        super(Encoder, self).__init__()
        self.use_encoder_idx = use_encoder_idx
        self.hidden_dim = hidden_dim
        self.num_encoder_layers = num_encoder_layers
        encoder_layer = TransformerEncoderLayer(
            hidden_dim,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
        )

        self.encoder = nn.ModuleList([
            TransformerEncoder(copy.deepcopy(encoder_layer), num_encoder_layers) for _ in range(use_encoder_idx)
        ])

    def forward(self, src, src_mask=None, pos_embed=None):
        for i in range(self.use_encoder_idx):
            h, w = src.shape[2:]
            # flatten [B, C, H, W] to [B, HxW, C]
            src_flatten = src.flatten(2).permute(0, 2, 1)
            if self.training:

                pos_embed = build_2d_sincos_position_embedding(w, h, self.hidden_dim)
            else:
                # pos_embed = getattr(self, f'pos_embed', None)
                pos_embed = build_2d_sincos_position_embedding(w, h, self.hidden_dim)
            memory = self.encoder[i](src_flatten, pos_embed=pos_embed)
            # memory = self.encoder[i](src_flatten)
            src = memory.permute(0, 2, 1).reshape(-1, self.hidden_dim, h, w).contiguous()
        return src
    # @staticmethod
    # def build_2d_sincos_position_embedding(w, h, embed_dim=256, temperature=10000.):
    #     '''
    #     tensor([ 0.,  1.,  2.,  3.,  4.,  5.,  6.,  7.,  8.,  9., 10., 11., 12., 13.,
    #     14., 15., 16., 17., 18., 19.])
    #     '''
    #     grid_w = torch.arange(int(w), dtype=torch.float16)
    #     grid_h = torch.arange(int(h), dtype=torch.float16)
    #     grid_w, grid_h = torch.meshgrid(grid_w, grid_h, indexing='ij')
    #     assert embed_dim % 4 == 0, \
    #         'Embed dimension must be divisible by 4 for 2D sin-cos position embedding'
    #     pos_dim = embed_dim // 4
    #     omega = torch.arange(pos_dim, dtype=torch.float16) / pos_dim
    #     omega = 1. / (temperature ** omega)
    #
    #     out_w = grid_w.flatten()[..., None] @ omega[None]
    #     out_h = grid_h.flatten()[..., None] @ omega[None]
    #
    #     return torch.concat([out_w.sin(), out_w.cos(), out_h.sin(), out_h.cos()], dim=1)[None, :, :]

    # def build_2d_sincos_position_embedding(w, h, embed_dim=256, temperature=10000.):
    #     '''
    #     tensor([ 0.,  1.,  2.,  3.,  4.,  5.,  6.,  7.,  8.,  9., 10., 11., 12., 13.,
    #     14., 15., 16., 17., 18., 19.])
    #     '''
    #     grid_w = torch.arange(int(w), dtype=torch.float32)
    #     grid_h = torch.arange(int(h), dtype=torch.float32)
    #     grid_w, grid_h = torch.meshgrid(grid_w, grid_h, indexing='ij')
    #     assert embed_dim % 4 == 0, \
    #         'Embed dimension must be divisible by 4 for 2D sin-cos position embedding'
    #     pos_dim = embed_dim // 4
    #     omega = torch.arange(pos_dim, dtype=torch.float32) / pos_dim
    #     omega = 1. / (temperature ** omega)
    #
    #     out_w = grid_w.flatten()[..., None] @ omega[None]
    #     out_h = grid_h.flatten()[..., None] @ omega[None]
    #
    #     return torch.concat([out_w.sin(), out_w.cos(), out_h.sin(), out_h.cos()], dim=1)[None, :, :]


class TransformerLayer(nn.Module):
    # Transformer layer https://arxiv.org/abs/2010.11929 (LayerNorm layers removed for better performance)
    def __init__(self, c, num_heads):
        super().__init__()
        self.q = nn.Linear(c, c, bias=False)
        self.k = nn.Linear(c, c, bias=False)
        self.v = nn.Linear(c, c, bias=False)
        self.ma = nn.MultiheadAttention(embed_dim=c, num_heads=num_heads)
        self.fc1 = nn.Linear(c, c, bias=False)
        self.fc2 = nn.Linear(c, c, bias=False)

    def forward(self, x):
        x = self.ma(self.q(x), self.k(x), self.v(x))[0] + x
        x = self.fc2(self.fc1(x)) + x
        return x


class TransformerBlock(nn.Module):
    # Vision Transformer https://arxiv.org/abs/2010.11929
    def __init__(self, c1, c2, num_heads, num_layers):
        super().__init__()
        self.conv = None
        if c1 != c2:
            self.conv = Conv(c1, c2)
        self.linear = nn.Linear(c2, c2)  # learnable position embedding
        self.tr = nn.Sequential(*[TransformerLayer(c2, num_heads) for _ in range(num_layers)])
        self.c2 = c2

    def forward(self, x):
        if self.conv is not None:
            x = self.conv(x)
        b, _, w, h = x.shape
        p = x.flatten(2)
        p = p.unsqueeze(0)
        p = p.transpose(0, 3)
        p = p.squeeze(3)
        e = self.linear(p)
        x = p + e

        x = self.tr(x)
        x = x.unsqueeze(3)
        x = x.transpose(0, 3)
        x = x.reshape(b, self.c2, w, h)
        return x


class Bottleneck(nn.Module):
    # Standard bottleneck
    def __init__(self, c1, c2, shortcut=True, g=1, e=0.5):  # ch_in, ch_out, shortcut, groups, expansion
        super(Bottleneck, self).__init__()
        c_ = int(c2 * e)  # hidden channels
        self.cv1 = Conv(c1, c_, 1, 1)
        self.cv2 = Conv(c_, c2, 3, 1, g=g)
        self.add = shortcut and c1 == c2

    def forward(self, x):
        return x + self.cv2(self.cv1(x)) if self.add else self.cv2(self.cv1(x))


class BottleneckCSP(nn.Module):
    # CSP Bottleneck https://github.com/WongKinYiu/CrossStagePartialNetworks
    def __init__(self, c1, c2, n=1, shortcut=True, g=1, e=0.5):  # ch_in, ch_out, number, shortcut, groups, expansion
        super(BottleneckCSP, self).__init__()
        c_ = int(c2 * e)  # hidden channels
        self.cv1 = Conv(c1, c_, 1, 1)
        self.cv2 = nn.Conv2d(c1, c_, 1, 1, bias=False)
        self.cv3 = nn.Conv2d(c_, c_, 1, 1, bias=False)
        self.cv4 = Conv(2 * c_, c2, 1, 1)
        self.bn = nn.BatchNorm2d(2 * c_)  # applied to cat(cv2, cv3)
        self.act = nn.LeakyReLU(0.1, inplace=True)
        self.m = nn.Sequential(*[Bottleneck(c_, c_, shortcut, g, e=1.0) for _ in range(n)])

    def forward(self, x):
        y1 = self.cv3(self.m(self.cv1(x)))
        y2 = self.cv2(x)
        return self.cv4(self.act(self.bn(torch.cat((y1, y2), dim=1))))


class C3(nn.Module):
    # CSP Bottleneck with 3 convolutions
    def __init__(self, c1, c2, n=1, shortcut=True, g=1, e=0.5):  # ch_in, ch_out, number, shortcut, groups, expansion
        super(C3, self).__init__()
        c_ = int(c2 * e)  # hidden channels
        self.cv1 = Conv(c1, c_, 1, 1)
        self.cv2 = Conv(c1, c_, 1, 1)
        self.cv3 = Conv(2 * c_, c2, 1)  # act=FReLU(c2)
        self.m = nn.Sequential(*[Bottleneck(c_, c_, shortcut, g, e=1.0) for _ in range(n)])
        # self.m = nn.Sequential(*[CrossConv(c_, c_, 3, 1, g, 1.0, shortcut) for _ in range(n)])

    def forward(self, x):
        return self.cv3(torch.cat((self.m(self.cv1(x)), self.cv2(x)), dim=1))


class C3TR(C3):
    # C3 module with TransformerBlock()
    def __init__(self, c1, c2, n=1, shortcut=True, g=1, e=0.5):
        super().__init__(c1, c2, n, shortcut, g, e)
        c_ = int(c2 * e)
        self.m = TransformerBlock(c_, c_, 4, n)


class SPPF(nn.Module):
    # Spatial Pyramid Pooling - Fast (SPPF) layer for YOLOv5 by Glenn Jocher
    def __init__(self, c1, c2, k=5):  # equivalent to SPP(k=(5, 9, 13))
        super().__init__()
        c_ = c1 // 2  # hidden channels
        self.cv1 = Conv(c1, c_, 1, 1)
        self.cv2 = Conv(c_ * 4, c2, 1, 1)
        self.m = nn.MaxPool2d(kernel_size=k, stride=1, padding=k // 2)

    def forward(self, x):
        x = self.cv1(x)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')  # suppress torch 1.9.0 max_pool2d() warning
            y1 = self.m(x)
            y2 = self.m(y1)
            return self.cv2(torch.cat([x, y1, y2, self.m(y2)], 1))


class SPP(nn.Module):
    # Spatial pyramid pooling layer used in YOLOv3-SPP
    def __init__(self, c1, c2, k=(5, 9, 13)):
        super(SPP, self).__init__()
        c_ = c1 // 2  # hidden channels
        self.cv1 = Conv(c1, c_, 1, 1)
        self.cv2 = Conv(c_ * (len(k) + 1), c2, 1, 1)
        self.m = nn.ModuleList([nn.MaxPool2d(kernel_size=x, stride=1, padding=x // 2) for x in k])

    def forward(self, x):
        x = self.cv1(x)
        return self.cv2(torch.cat([x] + [m(x) for m in self.m], 1))


class Focus(nn.Module):
    # Focus wh information into c-space
    def __init__(self, c1, c2, k=1, s=1, p=None, g=1, act=True):  # ch_in, ch_out, kernel, stride, padding, groups
        super(Focus, self).__init__()
        # print("c1 * 4, c2, k", c1 * 4, c2, k)
        self.conv = Conv(c1 * 4, c2, k, s, p, g, act)
        # self.contract = Contract(gain=2)

    def forward(self, x):  # x(b,c,w,h) -> y(b,4c,w/2,h/2)
        # print("Focus inputs shape", x.shape)
        # print()
        return self.conv(torch.cat([x[..., ::2, ::2], x[..., 1::2, ::2], x[..., ::2, 1::2], x[..., 1::2, 1::2]], 1))
        # return self.conv(self.contract(x))


class Contract(nn.Module):
    # Contract width-height into channels, i.e. x(1,64,80,80) to x(1,256,40,40)
    def __init__(self, gain=2):
        super().__init__()
        self.gain = gain

    def forward(self, x):
        N, C, H, W = x.size()  # assert (H / s == 0) and (W / s == 0), 'Indivisible gain'
        s = self.gain
        x = x.view(N, C, H // s, s, W // s, s)  # x(1,64,40,2,40,2)
        x = x.permute(0, 3, 5, 1, 2, 4).contiguous()  # x(1,2,2,64,40,40)
        return x.view(N, C * s * s, H // s, W // s)  # x(1,256,40,40)


class Expand(nn.Module):
    # Expand channels into width-height, i.e. x(1,64,80,80) to x(1,16,160,160)
    def __init__(self, gain=2):
        super().__init__()
        self.gain = gain

    def forward(self, x):
        N, C, H, W = x.size()  # assert C / s ** 2 == 0, 'Indivisible gain'
        s = self.gain
        x = x.view(N, s, s, C // s ** 2, H, W)  # x(1,2,2,16,80,80)
        x = x.permute(0, 3, 4, 1, 5, 2).contiguous()  # x(1,16,80,2,80,2)
        return x.view(N, C // s ** 2, H * s, W * s)  # x(1,16,160,160)


class Concat(nn.Module):
    # Concatenate a list of tensors along dimension
    def __init__(self, dimension=1):
        super(Concat, self).__init__()
        self.d = dimension

    def forward(self, x):
        # print(x.shape)
        return torch.cat(x, self.d)


class Add(nn.Module):
    #  Add two tensors
    def __init__(self, arg):
        super(Add, self).__init__()
        self.arg = arg

    def forward(self, x):
        return torch.add(x[0], x[1])


class Convfuision(nn.Module):
    #  Add two tensors
    def __init__(self, d_model, number):
        super().__init__()

        self.conv = nn.Conv2d(d_model * 2, d_model, kernel_size=1, stride=1, padding=0)

    def forward(self, x):
        r = torch.cat([x[0], x[1]], dim=1)
        t1 = self.conv(r)
        return t1


# class Add2(nn.Module):
#     #  x + transformer[0] or x + transformer[1]
#     def __init__(self, c1, index):
#         super().__init__()
#         self.index = index
#         self.conv= nn.Conv2d(c1 *2, c1, kernel_size=1, stride=1, padding=0)

#     def forward(self, x):
#         if self.index == 0:

#             r =  torch.cat([x[0], x[1][0]],dim=1)
#             t1 = self.conv(r)
#             return t1

#         elif self.index == 1:

#             r =  torch.cat([x[0], x[1][1]],dim=1)
#             t1 = self.conv(r)
#             return t1
# return torch.add(x[0], x[1])

class Add2(nn.Module):
    #  x + transformer[0] or x + transformer[1]
    def __init__(self, c1, index):
        super().__init__()
        self.index = index

    def forward(self, x):
        if self.index == 0:
            return torch.add(x[0], x[1][0])
        elif self.index == 1:
            return torch.add(x[0], x[1][1])
        # return torch.add(x[0], x[1])


class NMS(nn.Module):
    # Non-Maximum Suppression (NMS) module
    conf = 0.25  # confidence threshold
    iou = 0.45  # IoU threshold
    classes = None  # (optional list) filter by class

    def __init__(self):
        super(NMS, self).__init__()

    def forward(self, x):
        return non_max_suppression(x[0], conf_thres=self.conf, iou_thres=self.iou, classes=self.classes)


class autoShape(nn.Module):
    # input-robust model wrapper for passing cv2/np/PIL/torch inputs. Includes preprocessing, inference and NMS
    conf = 0.25  # NMS confidence threshold
    iou = 0.45  # NMS IoU threshold
    classes = None  # (optional list) filter by class

    def __init__(self, model):
        super(autoShape, self).__init__()
        self.model = model.eval()

    def autoshape(self):
        print('autoShape already enabled, skipping... ')  # model already converted to model.autoshape()
        return self

    @torch.no_grad()
    def forward(self, imgs, size=640, augment=False, profile=False):
        # Inference from various sources. For height=640, width=1280, RGB images example inputs are:
        #   filename:   imgs = 'data/images/zidane.jpg'
        #   URI:             = 'https://github.com/ultralytics/yolov5/releases/download/v1.0/zidane.jpg'
        #   OpenCV:          = cv2.imread('image.jpg')[:,:,::-1]  # HWC BGR to RGB x(640,1280,3)
        #   PIL:             = Image.open('image.jpg')  # HWC x(640,1280,3)
        #   numpy:           = np.zeros((640,1280,3))  # HWC
        #   torch:           = torch.zeros(16,3,320,640)  # BCHW (scaled to size=640, 0-1 values)
        #   multiple:        = [Image.open('image1.jpg'), Image.open('image2.jpg'), ...]  # list of images

        t = [time_synchronized()]
        p = next(self.model.parameters())  # for device and type
        if isinstance(imgs, torch.Tensor):  # torch
            with amp.autocast(enabled=p.device.type != 'cpu'):
                return self.model(imgs.to(p.device).type_as(p), augment, profile)  # inference

        # Pre-process
        n, imgs = (len(imgs), imgs) if isinstance(imgs, list) else (1, [imgs])  # number of images, list of images
        shape0, shape1, files = [], [], []  # image and inference shapes, filenames
        for i, im in enumerate(imgs):
            f = f'image{i}'  # filename
            if isinstance(im, str):  # filename or uri
                im, f = np.asarray(Image.open(requests.get(im, stream=True).raw if im.startswith('http') else im)), im
            elif isinstance(im, Image.Image):  # PIL Image
                im, f = np.asarray(im), getattr(im, 'filename', f) or f
            files.append(Path(f).with_suffix('.jpg').name)
            if im.shape[0] < 5:  # image in CHW
                im = im.transpose((1, 2, 0))  # reverse dataloader .transpose(2, 0, 1)
            im = im[:, :, :3] if im.ndim == 3 else np.tile(im[:, :, None], 3)  # enforce 3ch input
            s = im.shape[:2]  # HWC
            shape0.append(s)  # image shape
            g = (size / max(s))  # gain
            shape1.append([y * g for y in s])
            imgs[i] = im if im.data.contiguous else np.ascontiguousarray(im)  # update
        shape1 = [make_divisible(x, int(self.stride.max())) for x in np.stack(shape1, 0).max(0)]  # inference shape
        x = [letterbox(im, new_shape=shape1, auto=False)[0] for im in imgs]  # pad
        x = np.stack(x, 0) if n > 1 else x[0][None]  # stack
        x = np.ascontiguousarray(x.transpose((0, 3, 1, 2)))  # BHWC to BCHW
        x = torch.from_numpy(x).to(p.device).type_as(p) / 255.  # uint8 to fp16/32
        t.append(time_synchronized())

        with amp.autocast(enabled=p.device.type != 'cpu'):
            # Inference
            y = self.model(x, augment, profile)[0]  # forward
            t.append(time_synchronized())

            # Post-process
            y = non_max_suppression(y, conf_thres=self.conf, iou_thres=self.iou, classes=self.classes)  # NMS
            for i in range(n):
                scale_coords(shape1, y[i][:, :4], shape0[i])

            t.append(time_synchronized())
            return Detections(imgs, y, files, t, self.names, x.shape)


class Detections:
    # detections class for YOLOv5 inference results
    def __init__(self, imgs, pred, files, times=None, names=None, shape=None):
        super(Detections, self).__init__()
        d = pred[0].device  # device
        gn = [torch.tensor([*[im.shape[i] for i in [1, 0, 1, 0]], 1., 1.], device=d) for im in imgs]  # normalizations
        self.imgs = imgs  # list of images as numpy arrays
        self.pred = pred  # list of tensors pred[0] = (xyxy, conf, cls)
        self.names = names  # class names
        self.files = files  # image filenames
        self.xyxy = pred  # xyxy pixels
        self.xywh = [xyxy2xywh(x) for x in pred]  # xywh pixels
        self.xyxyn = [x / g for x, g in zip(self.xyxy, gn)]  # xyxy normalized
        self.xywhn = [x / g for x, g in zip(self.xywh, gn)]  # xywh normalized
        self.n = len(self.pred)  # number of images (batch size)
        self.t = tuple((times[i + 1] - times[i]) * 1000 / self.n for i in range(3))  # timestamps (ms)
        self.s = shape  # inference BCHW shape

    def display(self, pprint=False, show=False, save=False, crop=False, render=False, save_dir=Path('')):
        for i, (im, pred) in enumerate(zip(self.imgs, self.pred)):
            str = f'image {i + 1}/{len(self.pred)}: {im.shape[0]}x{im.shape[1]} '
            if pred is not None:
                for c in pred[:, -1].unique():
                    n = (pred[:, -1] == c).sum()  # detections per class
                    str += f"{n} {self.names[int(c)]}{'s' * (n > 1)}, "  # add to string
                if show or save or render or crop:
                    for *box, conf, cls in pred:  # xyxy, confidence, class
                        label = f'{self.names[int(cls)]} {conf:.2f}'
                        if crop:
                            save_one_box(box, im, file=save_dir / 'crops' / self.names[int(cls)] / self.files[i])
                        else:  # all others
                            plot_one_box(box, im, label=label, color=colors(cls))

            im = Image.fromarray(im.astype(np.uint8)) if isinstance(im, np.ndarray) else im  # from np
            if pprint:
                print(str.rstrip(', '))
            if show:
                im.show(self.files[i])  # show
            if save:
                f = self.files[i]
                im.save(save_dir / f)  # save
                print(f"{'Saved' * (i == 0)} {f}", end=',' if i < self.n - 1 else f' to {save_dir}\n')
            if render:
                self.imgs[i] = np.asarray(im)

    def print(self):
        self.display(pprint=True)  # print results
        print(f'Speed: %.1fms pre-process, %.1fms inference, %.1fms NMS per image at shape {tuple(self.s)}' % self.t)

    def show(self):
        self.display(show=True)  # show results

    def save(self, save_dir='runs/hub/exp'):
        save_dir = increment_path(save_dir, exist_ok=save_dir != 'runs/hub/exp', mkdir=True)  # increment save_dir
        self.display(save=True, save_dir=save_dir)  # save results

    def crop(self, save_dir='runs/hub/exp'):
        save_dir = increment_path(save_dir, exist_ok=save_dir != 'runs/hub/exp', mkdir=True)  # increment save_dir
        self.display(crop=True, save_dir=save_dir)  # crop results
        print(f'Saved results to {save_dir}\n')

    def render(self):
        self.display(render=True)  # render results
        return self.imgs

    def pandas(self):
        # return detections as pandas DataFrames, i.e. print(results.pandas().xyxy[0])
        new = copy(self)  # return copy
        ca = 'xmin', 'ymin', 'xmax', 'ymax', 'confidence', 'class', 'name'  # xyxy columns
        cb = 'xcenter', 'ycenter', 'width', 'height', 'confidence', 'class', 'name'  # xywh columns
        for k, c in zip(['xyxy', 'xyxyn', 'xywh', 'xywhn'], [ca, ca, cb, cb]):
            a = [[x[:5] + [int(x[5]), self.names[int(x[5])]] for x in x.tolist()] for x in getattr(self, k)]  # update
            setattr(new, k, [pd.DataFrame(x, columns=c) for x in a])
        return new

    def tolist(self):
        # return a list of Detections objects, i.e. 'for result in results.tolist():'
        x = [Detections([self.imgs[i]], [self.pred[i]], self.names, self.s) for i in range(self.n)]
        for d in x:
            for k in ['imgs', 'pred', 'xyxy', 'xyxyn', 'xywh', 'xywhn']:
                setattr(d, k, getattr(d, k)[0])  # pop out of list
        return x

    def __len__(self):
        return self.n


class Classify(nn.Module):
    # Classification head, i.e. x(b,c1,20,20) to x(b,c2)
    def __init__(self, c1, c2, k=1, s=1, p=None, g=1):  # ch_in, ch_out, kernel, stride, padding, groups
        super(Classify, self).__init__()
        self.aap = nn.AdaptiveAvgPool2d(1)  # to x(b,c1,1,1)
        self.conv = nn.Conv2d(c1, c2, k, s, autopad(k, p), groups=g)  # to x(b,c2,1,1)
        self.flat = nn.Flatten()

    def forward(self, x):
        z = torch.cat([self.aap(y) for y in (x if isinstance(x, list) else [x])], 1)  # cat if list
        return self.flat(self.conv(z))  # flatten to x(b,c2)


class SelfAttention(nn.Module):
    """
     Multi-head masked self-attention layer
    """

    def __init__(self, d_model, d_k, d_v, h, sr_ratio, attn_pdrop=.1, resid_pdrop=.1):
        '''
        :param d_model: Output dimensionality of the model  =  channel
        :param d_k: Dimensionality of queries and keys
        :param d_v: Dimensionality of values
        :param h: Number of heads
        '''
        super(SelfAttention, self).__init__()
        assert d_k % h == 0
        self.d_model = d_model
        self.d_k = d_model // h
        self.d_v = d_model // h
        self.num_heads = h

        self.scale = self.d_v ** -0.5

        # key, query, value projections for all heads
        self.q = nn.Linear(d_model, d_model)
        self.kv = nn.Linear(d_model, d_model * 2)
        self.attn_drop = nn.Dropout(attn_pdrop)
        self.proj = nn.Linear(d_model, d_model)
        self.proj_drop = nn.Dropout(resid_pdrop)

        self.kv = nn.Linear(d_model, d_model * 2)

        self.sr_ratio = sr_ratio
        # 实现上这里等价于一个卷积层
        if sr_ratio > 1:
            self.sr = nn.Conv2d(d_model, d_model, kernel_size=sr_ratio, stride=sr_ratio)
            self.norm = nn.LayerNorm(d_model)

        self.init_weights()

    def init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                init.kaiming_normal_(m.weight, mode='fan_out')
                if m.bias is not None:
                    init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                init.constant_(m.weight, 1)
                init.constant_(m.bias, 0)
            elif isinstance(m, nn.Linear):
                init.normal_(m.weight, std=0.001)
                if m.bias is not None:
                    init.constant_(m.bias, 0)

    def forward(self, x, attention_mask=None, attention_weights=None):
        '''
        Computes Self-Attention
        Args:
            x (tensor): input (token) dim:(b_s, nx, c),
                b_s means batch size
                nx means length, for CNN, equals H*W, i.e. the length of feature maps
                c means channel, i.e. the channel of feature maps
            attention_mask: Mask over attention values (b_s, h, nq, nk). True indicates masking.
            attention_weights: Multiplicative weights for attention values (b_s, h, nq, nk).
        Return:
            output (tensor): dim:(b_s, nx, c)
        '''

        B, N, C = x.shape

        h = int(math.sqrt(N // 2))
        w = h

        q = self.q(x).reshape(B, N, self.num_heads, C // self.num_heads).permute(0, 2, 1, 3)

        if self.sr_ratio > 1:
            x_ = x.permute(0, 2, 1).reshape(B, C, N // 2, 2)

            x_1 = x_[:, :, :, 0].permute(0, 2, 1).reshape(B, C, h, w)

            x_2 = x_[:, :, :, 1].permute(0, 2, 1).reshape(B, C, h, w)
            x_ = torch.cat([x_1, x_2], dim=2)

            x_ = self.sr(x_).reshape(B, C, -1).permute(0, 2, 1)  # 这里x_.shape = (B, N/R^2, C)

            x_ = self.norm(x_)
            kv = self.kv(x_).reshape(B, -1, 2, self.num_heads, C // self.num_heads).permute(2, 0, 3, 1, 4)
        else:
            kv = self.kv(x).reshape(B, -1, 2, self.num_heads, C // self.num_heads).permute(2, 0, 3, 1, 4)
        k, v = kv[0], kv[1]

        attn = (q @ k.transpose(-2, -1)) * self.scale
        attn = attn.softmax(dim=-1)
        attn = self.attn_drop(attn)

        x = (attn @ v).transpose(1, 2).reshape(B, N, C)
        x = self.proj(x)
        out = self.proj_drop(x)

        return out


class myTransformerBlock(nn.Module):
    """ Transformer block """

    def __init__(self, d_model, d_k, d_v, h, block_exp, attn_pdrop, resid_pdrop, sr_ratio):
        """
        :param d_model: Output dimensionality of the model
        :param d_k: Dimensionality of queries and keys
        :param d_v: Dimensionality of values
        :param h: Number of heads
        :param block_exp: Expansion factor for MLP (feed foreword network)

        """
        super().__init__()
        self.ln_input = nn.LayerNorm(d_model)
        self.ln_output = nn.LayerNorm(d_model)
        self.sa = SelfAttention(d_model, d_k, d_v, h, sr_ratio, attn_pdrop, resid_pdrop)
        self.mlp = nn.Sequential(
            nn.Linear(d_model, block_exp * d_model),
            # nn.SiLU(),  # changed from GELU
            nn.GELU(),  # changed from GELU
            nn.Linear(block_exp * d_model, d_model),
            nn.Dropout(resid_pdrop),
        )

    def forward(self, x):
        bs, nx, c = x.size()

        x = x + self.sa(self.ln_input(x))
        x = x + self.mlp(self.ln_output(x))

        return x


class C2f(nn.Module):
    """Faster Implementation of CSP Bottleneck with 2 convolutions."""

    def __init__(self, c1, c2, n=2, shortcut=False, g=1, e=0.5):
        """Initializes a CSP bottleneck with 2 convolutions and n Bottleneck blocks for faster processing."""
        super().__init__()
        self.c = int(c2 * e)  # hidden channels
        if g != 1:
            self.g = int(g * e)
        else:
            self.g = g
        self.cv1 = Conv(c1, 2 * self.c, 1, 1)
        self.cv2 = Conv((2 + n) * self.c, c2, 1)  # optional act=FReLU(c2)
        self.m = nn.ModuleList(Bottleneck(self.c, self.c, shortcut, self.g, e=1.0) for _ in range(n))

    def forward(self, x):
        """Forward pass through C2f layer."""
        y = list(self.cv1(x).chunk(2, 1))
        y.extend(m(y[-1]) for m in self.m)
        return self.cv2(torch.cat(y, 1))

    def forward_split(self, x):
        """Forward pass using split() instead of chunk()."""
        y = list(self.cv1(x).split((self.c, self.c), 1))
        y.extend(m(y[-1]) for m in self.m)
        return self.cv2(torch.cat(y, 1))


# class Multiattention(nn.Module):
#     def __init__(self):
#         super().__init__()
class Icmp(nn.Module):
    def __init__(self, c1, g, vert_anchor):
        super().__init__()
        self.vert_anchor = vert_anchor
        self.c2f1 = C2f(c1, c1)
        self.c2f2 = C2f(c1, c1, g=g)

    def forward(self, x1, x2):
        b, wh, c = x1.size()
        x1 = x1.view(b, self.vert_anchor, self.vert_anchor, c).permute(0, 3, 1, 2)
        x2 = x2.view(b, c, self.vert_anchor, self.vert_anchor)
        x_1 = self.c2f1(x1)
        x_2 = self.c2f2(x2)
        sa_inform = x_1.view(b, c, -1).permute(0, 2, 1).contiguous()
        se_inform = x_2.view(b, c, -1).contiguous()
        return sa_inform, se_inform


class Transformer_sstrack(nn.Module):
    """ Transformer block """

    def __init__(self, d_model, d_k, d_v, vert_anchor, horz_anchors, h, block_exp, attn_pdrop, resid_pdrop, sr_ratio):
        """
        :param d_model: Output dimensionality of the model
        :param d_k: Dimensionality of queries and keys
        :param d_v: Dimensionality of values
        :param h: Number of heads
        :param block_exp: Expansion factor for MLP (feed foreword network)

        """
        super().__init__()
        self.ln_input_sa = nn.LayerNorm(d_model)
        self.ln_input_se = nn.LayerNorm(vert_anchor * horz_anchors)

        self.ln_output_sa = nn.LayerNorm(d_model)
        self.ln_output_se = nn.LayerNorm(vert_anchor * horz_anchors)
        self.icmp1 = Icmp(d_model, d_model, vert_anchor)
        self.icmp2 = Icmp(d_model, d_model, vert_anchor)
        self.sa1 = SelfAttention(d_model, d_k, d_v, h, sr_ratio, attn_pdrop, resid_pdrop)
        self.sa2 = SelfAttention(vert_anchor * horz_anchors, vert_anchor * horz_anchors, vert_anchor * horz_anchors, h,
                                 sr_ratio, attn_pdrop, resid_pdrop)
        self.mlp1 = nn.Sequential(
            nn.Linear(d_model, block_exp * d_model),
            # nn.SiLU(),  # changed from GELU
            nn.GELU(),  # changed from GELU
            nn.Linear(block_exp * d_model, d_model),
            nn.Dropout(resid_pdrop),
        )
        self.mlp2 = nn.Sequential(
            nn.Linear(vert_anchor * horz_anchors, block_exp * vert_anchor * horz_anchors),
            # nn.SiLU(),  # changed from GELU
            nn.GELU(),  # changed from GELU
            nn.Linear(block_exp * vert_anchor * horz_anchors, vert_anchor * horz_anchors),
            nn.Dropout(resid_pdrop),
        )

    def forward(self, x):
        n, bs, nx, c = x.size()
        sa_inform = x[0]
        se_inform = x[1].permute(0, 2, 1).contiguous()
        res_sa=sa_inform
        res_se=se_inform
        sa_norm = self.ln_input_sa(sa_inform)
        se_norm = self.ln_input_se(se_inform)
        sa_c2f, se_c2f = self.icmp1(sa_norm, se_norm)
        # sa_c2f, se_c2f = self.icmp1(sa_inform, se_inform)
        # sa_inform = sa_inform + self.sa1(sa_norm) + se_c2f.permute(0, 2, 1).contiguous()
        # se_inform = se_inform + self.sa2(se_norm) + sa_c2f.permute(0, 2, 1).contiguous()
        sa_inform = sa_inform + self.sa1(sa_norm)
        se_inform = se_inform + self.sa2(se_norm)
        sa_c2f2, se_c2f2 = self.icmp2(sa_inform, se_inform)
        sa_inform = sa_inform  + self.mlp1(self.ln_output_sa(sa_inform)) + se_c2f2.permute(0, 2, 1).contiguous()
        se_inform = se_inform + self.mlp2(self.ln_output_se(se_inform)) + sa_c2f2.permute(0, 2, 1).contiguous()
        # sa_inform = sa_inform  + self.mlp1(self.ln_output_sa(sa_inform)) + se_c2f.permute(0, 2, 1).contiguous()
        # se_inform = se_inform + self.mlp2(self.ln_output_se(se_inform)) + sa_c2f.permute(0, 2, 1).contiguous()
        # x = x + self.sa(self.ln_input(x))
        # x = x + self.mlp(self.ln_output(x))
        x = torch.stack([sa_inform, se_inform.permute(0, 2, 1)], dim=0)
        return x

#
# class GPT(nn.Module):
#     def __init__(self, d_model, sr_ratio, vert_anchors, horz_anchors, h=8, block_exp=4, n_layer=6,
#                  embd_pdrop=0.1, attn_pdrop=0.1, resid_pdrop=0.1):
#         super().__init__()
#         self.n_embd = d_model
#         self.d_model = d_model
#         d_k = d_model
#         d_v = d_model
#         self.vert_anchors = vert_anchors
#         self.horz_anchors = horz_anchors
#         self.ln_f = nn.LayerNorm(self.n_embd)
#         # regularization
#         self.drop = nn.Dropout(embd_pdrop)
#         self.pos_emb1 = nn.Parameter(torch.zeros(1, vert_anchors * horz_anchors, self.n_embd))
#         self.pos_emb2 = nn.Parameter(torch.zeros(1, self.n_embd, vert_anchors * horz_anchors))
#         self.avgpool = nn.AdaptiveAvgPool2d((self.vert_anchors, self.horz_anchors))
#         self.trans = nn.Sequential(*[
#             Transformer_sstrack(d_model, d_k, d_v, vert_anchors, horz_anchors, h, block_exp, attn_pdrop, resid_pdrop,
#                                 sr_ratio)
#             for layer in range(n_layer)])
#
#         self.S2Attention_all = S2Block(d_model * 2)
#         # self.SpatialAttention_all = SpatialAttention()
#         self.mapconv_rgb = nn.Conv2d(d_model * 2, d_model, kernel_size=1, stride=1, padding=0)
#         self.mapconv_ir = nn.Conv2d(d_model * 2, d_model, kernel_size=1, stride=1, padding=0)
#         # init weights
#         self.apply(self._init_weights)
#         self.norm = nn.LayerNorm(d_model * 2)
#
#     @staticmethod
#     def _init_weights(module):
#         if isinstance(module, nn.Linear):
#             module.weight.data.normal_(mean=0.0, std=0.02)
#             if module.bias is not None:
#                 module.bias.data.zero_()
#         elif isinstance(module, nn.LayerNorm):
#             module.bias.data.zero_()
#             module.weight.data.fill_(1.0)
#
#     def forward(self, x):
#         rgb_fea = x[0]  # rgb_fea (tensor): dim:(B, C, H, W)
#         ir_fea = x[1]  # ir_fea (tensor): dim:(B, C, H, W)
#         assert rgb_fea.shape[0] == ir_fea.shape[0]
#         bs, c, h, w = rgb_fea.shape
#         # -------------------------------------------------------------------------
#         # AvgPooling
#         # -------------------------------------------------------------------------
#         # AvgPooling for reduce the dimension due to expensive computation
#         rgb_fea = self.avgpool(rgb_fea)
#         ir_fea = self.avgpool(ir_fea)
#
#         # -------------------------------------------------------------------------
#         # Transformer
#         # -------------------------------------------------------------------------
#         # pad token embeddings along number of tokens dimension
#         rgb_fea_flat = rgb_fea.view(bs, c, -1).permute(0, 2, 1).contiguous()
#         rgb_fea_flat = rgb_fea_flat + self.pos_emb1  # flatten the feature
#         ir_fea_flat = ir_fea.view(bs, c, -1) + self.pos_emb2  # flatten the feature
#         ir_fea_flat = ir_fea_flat.permute(0, 2, 1).contiguous()
#         token_embedings = torch.stack([rgb_fea_flat, ir_fea_flat], dim=0)  # 2,b,64,256
#         x = self.trans(token_embedings)
#         sa_inform = x[0]
#         se_inform = x[1]
#         x = torch.cat([sa_inform, se_inform], dim=1).contiguous()
#         x = self.ln_f(x)  # dim:(B, 2*H*W, C)
#         x = x.view(bs, 2, self.vert_anchors, self.horz_anchors, self.n_embd)
#         x = x.permute(0, 1, 4, 2, 3)  # dim:(B, 2, C, H, W)
#
#         # 这样截取的方式, 是否采用映射的方式更加合理？
#         rgb_fea_out_map = x[:, 0, :, :, :].contiguous().view(bs, self.n_embd, self.vert_anchors, self.horz_anchors)
#         ir_fea_out_map = x[:, 1, :, :, :].contiguous().view(bs, self.n_embd, self.vert_anchors, self.horz_anchors)
#
#         # 映射的方式
#
#         all_fea_out = torch.cat([rgb_fea_out_map, ir_fea_out_map], dim=1)  # concat
#
#         all_fea_out = self.S2Attention_all(all_fea_out)
#         # all_fea_out = self.SpatialAttention_all(all_fea_out).permute(0,2,3,1)
#         # all_fea_out=self.norm(all_fea_out).permute(0,3,1,2)
#         rgb_fea_out = self.mapconv_rgb(all_fea_out)
#         ir_fea_out = self.mapconv_ir(all_fea_out)
#
#         # -------------------------------------------------------------------------
#         # Interpolate (or Upsample)
#         # -------------------------------------------------------------------------
#         rgb_fea_out = F.interpolate(rgb_fea_out, size=([h, w]), mode='bilinear')
#         ir_fea_out = F.interpolate(ir_fea_out, size=([h, w]), mode='bilinear')
#
#         return rgb_fea_out, ir_fea_out


class GPT(nn.Module):
    """  the full GPT language model, with a context size of block_size """
    # def __init__(self, d_model,sr_ratio, vert_anchors, horz_anchors,
    #                 h=8, block_exp=8,n_layer=8,
    def __init__(self, d_model,sr_ratio, vert_anchors, horz_anchors,
                    h=8, block_exp=4,n_layer=6,
                 embd_pdrop=0.1, attn_pdrop=0.1, resid_pdrop=0.1):
        super().__init__()

        self.n_embd = d_model
        self.vert_anchors = vert_anchors
        self.horz_anchors = horz_anchors

        d_k = d_model
        d_v = d_model

        # positional embedding parameter (learnable), rgb_fea + ir_fea
        self.pos_emb = nn.Parameter(torch.zeros(1, 2 * vert_anchors * horz_anchors, self.n_embd))

        # transformer
        self.trans_blocks = nn.Sequential(*[myTransformerBlock(d_model, d_k, d_v, h, block_exp, attn_pdrop, resid_pdrop,sr_ratio)
                                            for layer in range(n_layer)])

        # decoder head
        self.ln_f = nn.LayerNorm(self.n_embd)

        # regularization
        self.drop = nn.Dropout(embd_pdrop)

        # avgpool
        self.avgpool = nn.AdaptiveAvgPool2d((self.vert_anchors, self.horz_anchors))

        # 映射的方式

        self.S2Attention_all =  S2Block(d_model *2 )
        # self.SpatialAttention_all = SpatialAttention()
        self.mapconv_rgb = nn.Conv2d(d_model *2, d_model, kernel_size=1, stride=1, padding=0)
        self.mapconv_ir = nn.Conv2d(d_model *2, d_model, kernel_size=1, stride=1, padding=0)
        # init weights
        self.apply(self._init_weights)
        self.norm=nn.LayerNorm(d_model*2)

    @staticmethod
    def _init_weights(module):
        if isinstance(module, nn.Linear):
            module.weight.data.normal_(mean=0.0, std=0.02)
            if module.bias is not None:
                module.bias.data.zero_()
        elif isinstance(module, nn.LayerNorm):
            module.bias.data.zero_()
            module.weight.data.fill_(1.0)

    def forward(self, x):
        """
        Args:
            x (tuple?)

        """
        rgb_fea = x[0]  # rgb_fea (tensor): dim:(B, C, H, W)
        ir_fea = x[1]   # ir_fea (tensor): dim:(B, C, H, W)
        assert rgb_fea.shape[0] == ir_fea.shape[0]
        bs, c, h, w = rgb_fea.shape

        # -------------------------------------------------------------------------
        # AvgPooling
        # -------------------------------------------------------------------------
        # AvgPooling for reduce the dimension due to expensive computation
        rgb_fea = self.avgpool(rgb_fea)
        ir_fea = self.avgpool(ir_fea)

        # -------------------------------------------------------------------------
        # Transformer
        # -------------------------------------------------------------------------
        # pad token embeddings along number of tokens dimension
        rgb_fea_flat = rgb_fea.view(bs, c, -1)  # flatten the feature
        ir_fea_flat = ir_fea.view(bs, c, -1)  # flatten the feature
        token_embeddings = torch.cat([rgb_fea_flat, ir_fea_flat], dim=2)  # concat
        token_embeddings = token_embeddings.permute(0, 2, 1).contiguous()  # dim:(B, 2*H*W, C)

        # transformer
        x = self.drop(self.pos_emb + token_embeddings)  # sum positional embedding and token    dim:(B, 2*H*W, C)
        x = self.trans_blocks(x)  # dim:(B, 2*H*W, C)

        # decoder head
        x = self.ln_f(x)  # dim:(B, 2*H*W, C)
        x = x.view(bs, 2, self.vert_anchors, self.horz_anchors, self.n_embd)
        x = x.permute(0, 1, 4, 2, 3)  # dim:(B, 2, C, H, W)

        # 这样截取的方式, 是否采用映射的方式更加合理？
        rgb_fea_out_map = x[:, 0, :, :, :].contiguous().view(bs, self.n_embd, self.vert_anchors, self.horz_anchors)
        ir_fea_out_map = x[:, 1, :, :, :].contiguous().view(bs, self.n_embd, self.vert_anchors, self.horz_anchors)

        #映射的方式

        all_fea_out = torch.cat([rgb_fea_out_map, ir_fea_out_map], dim=1)  # concat


        all_fea_out = self.S2Attention_all(all_fea_out)
        # all_fea_out = self.SpatialAttention_all(all_fea_out).permute(0,2,3,1)
        # all_fea_out=self.norm(all_fea_out).permute(0,3,1,2)
        rgb_fea_out = self.mapconv_rgb(all_fea_out)
        ir_fea_out= self.mapconv_ir(all_fea_out)


        # -------------------------------------------------------------------------
        # Interpolate (or Upsample)
        # -------------------------------------------------------------------------
        rgb_fea_out = F.interpolate(rgb_fea_out, size=([h, w]), mode='bilinear')
        ir_fea_out = F.interpolate(ir_fea_out, size=([h, w]), mode='bilinear')

        return rgb_fea_out, ir_fea_out


def spatial_shift1(x):
    b, w, h, c = x.size()
    x[:, 1:, :, :c // 4] = x[:, :w - 1, :, :c // 4]
    x[:, :w - 1, :, c // 4:c // 2] = x[:, 1:, :, c // 4:c // 2]
    x[:, :, 1:, c // 2:c * 3 // 4] = x[:, :, :h - 1, c // 2:c * 3 // 4]
    x[:, :, :h - 1, 3 * c // 4:] = x[:, :, 1:, 3 * c // 4:]
    return x


def spatial_shift2(x):
    b, w, h, c = x.size()
    x[:, :, 1:, :c // 4] = x[:, :, :h - 1, :c // 4]
    x[:, :, :h - 1, c // 4:c // 2] = x[:, :, 1:, c // 4:c // 2]
    x[:, 1:, :, c // 2:c * 3 // 4] = x[:, :w - 1, :, c // 2:c * 3 // 4]
    x[:, :w - 1, :, 3 * c // 4:] = x[:, 1:, :, 3 * c // 4:]
    return x


class SplitAttention(nn.Module):
    def __init__(self, channel, k=3):
        super().__init__()
        self.channel = channel
        self.k = k
        self.mlp1 = nn.Linear(channel, channel, bias=False)
        self.gelu = nn.GELU()
        self.mlp2 = nn.Linear(channel, channel * k, bias=False)
        self.softmax = nn.Softmax(1)

    def forward(self, x_all):
        b, k, h, w, c = x_all.shape
        x_all = x_all.reshape(b, k, -1, c)
        a = torch.sum(torch.sum(x_all, 1), 1)
        hat_a = self.mlp2(self.gelu(self.mlp1(a)))
        hat_a = hat_a.reshape(b, self.k, c)
        bar_a = self.softmax(hat_a)
        attention = bar_a.unsqueeze(-2)
        out = attention * x_all
        out = torch.sum(out, 1).reshape(b, h, w, c)
        return out


class S2Attention(nn.Module):

    def __init__(self, channels):
        super().__init__()
        self.mlp1 = nn.Linear(channels, channels * 3)
        self.mlp2 = nn.Linear(channels, channels)
        self.split_attention = SplitAttention(channels)

    def forward(self, x):
        b, h, w, c = x.size()
        # x=x.permute(0,2,3,1)
        x = self.mlp1(x)
        x1 = spatial_shift1(x[:, :, :, :c])
        x2 = spatial_shift2(x[:, :, :, c:c * 2])
        x3 = x[:, :, :, c * 2:]
        x_all = torch.stack([x1, x2, x3], 1)
        a = self.split_attention(x_all)
        x = self.mlp2(a)
        # x=x.permute(0,3,1,2)
        return x


# class SpatialAttention(nn.Module):
#     def __init__(self,bias=False):
#         super().__init__()
#         self.conv=nn.Conv2d(2,1,kernel_size=7,padding=(7-1)//2,bias=bias)
#         self.softmax=nn.Softmax(2)
#     def forward(self,x):
#         b,c,h,w=x.size()
#         max_pool=torch.max(x,dim=1,keepdim=True)[0]
#         mean_pool = torch.mean(x, dim=1, keepdim=True)
#         pool_cat=torch.cat([max_pool,mean_pool],dim=1)
#
#         map=self.conv(pool_cat).view(b,1,-1)
#
#
#         atten=self.softmax(map).view(b,1,h,w)
#         x=x*atten
#
#         return x
# class SpatialAttention(nn.Module):
#     def __init__(self, bias=False):
#         super().__init__()
#         self.conv = nn.Conv2d(2, 1, kernel_size=7, padding=(7 - 1) // 2, bias=bias)
#         self.softmax = nn.Softmax(2)
#
#     def forward(self, x):
#         b, h, w, c = x.size()
#         max_pool = torch.max(x, dim=3, keepdim=True)[0]
#         mean_pool = torch.mean(x, dim=3, keepdim=True)
#         pool_cat = torch.cat([max_pool, mean_pool], dim=3)
#         pool_cat_conv = pool_cat.permute(0, 3, 1, 2)
#         map = self.conv(pool_cat_conv).view(b, 1, -1)
#         atten = self.softmax(map).view(b, h, w, 1)
#         # x=x*atten
#
#         x = x * atten
#         return x


class S2Block(nn.Module):
    def __init__(self, d_model, depth=1, expansion_factor=4, dropout=0.):
        super().__init__()

        self.model = nn.Sequential(
            *[nn.Sequential(
                PreNormResidual(d_model, S2Attention(d_model)),
            ) for _ in range(depth)]
        )
        self.norm = nn.LayerNorm(d_model)

    def forward(self, x):
        x = x.permute(0, 2, 3, 1)
        x = self.model(x)

        x = self.norm(x)
        x = x.permute(0, 3, 1, 2)
        return x


class PreNormResidual(nn.Module):
    def __init__(self, dim, fn):
        super().__init__()
        self.fn = fn
        self.norm = nn.LayerNorm(dim)

    def forward(self, x):
        return self.fn(self.norm(x)) + x