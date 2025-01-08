from pathlib import Path
import torch
import pickle
import numpy as np
import matplotlib.pyplot as plt
from utils.plots import plot_images, output_to_target, plot_study_txt
if __name__ == '__main__':
    img_f='test_batch0_labels.jpg'
    f=Path(img_f)
    img=torch.load("image.pt")
    targets=torch.load("targets.pt")

    f_read = open("path.pkl", 'rb')
    paths = pickle.load(f_read)
    f_read.close()
    f_read2 = open("name.pkl", 'rb')
    names = pickle.load(f_read2)
    f_read2.close()
    # print(paths
    plot_images(img,targets,paths,f,names)