import torch
from models.common import SelfAttention
from models.common import GPT
x=torch.rand(2,3,256, 80,80)


# sa = SelfAttention(64, 64, 64, 8,1, 0.1, 0.1)
# x2=sa(x1)
# print(x2.shape)
# # x1=x1.permute(0,2,1)
# x2=torch.stack([x,x1],dim=0)
model=GPT(256,1,8,8)
x1,x2=model(x)
# x3=torch.cat([x2[0],x2[1]],dim=1)
print(x1.shape)
print(x2.shape)
# model = SpatialAttention()
# atten=model(x)
# print(atten.shape)