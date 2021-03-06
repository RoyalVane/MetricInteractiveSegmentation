import PIL
import PIL.Image
import numpy as np

import torch
from torch.utils import data
from torchvision import transforms

import os


def normalize_image_imagenet(img, channel_order=False):
    if channel_order:
        img[0, :, :] = (img[0, :, :] - 0.485) / 0.229
        img[1, :, :] = (img[1, :, :] - 0.456) / 0.224
        img[2, :, :] = (img[2, :, :] - 0.406) / 0.225
    else:
        img[:, :, 0] = (img[:, :, 0] - 0.485) / 0.229
        img[:, :, 1] = (img[:, :, 1] - 0.456) / 0.224
        img[:, :, 2] = (img[:, :, 2] - 0.406) / 0.225

    return img

class GrabCut(data.Dataset):
    """Data loader for the Pascal VOC semantic segmentation dataset.
    """

    def __init__(
            self,
            *,
            grabcut_root,
            normalize=True
    ):
        self.grabcut_root = grabcut_root
        self.normalize = normalize
        
        if self.normalize:
            self.transforms = transforms.Compose([transforms.ToTensor(),
                                                  transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                                                       std=[0.229, 0.224, 0.225])])
        else:
            self.transforms = transforms.Compose([transforms.ToTensor()])

        with open(os.path.join(grabcut_root, 'dataset.txt')) as file:
            lines = file.readlines()
            self.dataset = [line.rstrip('\n').split() for line in lines]

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, i):
        img = PIL.Image.open(self.grabcut_root + self.dataset[i][0])
        lbl = np.array(PIL.Image.open(self.grabcut_root + self.dataset[i][1]))

        img = self.transforms(img)

        lbl[lbl == 255] = 1
        lbl[lbl == 128] = 255

        return img, torch.from_numpy(lbl)

