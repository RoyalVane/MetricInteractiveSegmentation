
import torch
import torch.utils.data as data
import torch.nn as nn
import torch.optim as optim
import collections
import os
import socket

from datetime import datetime
import timeit

import deeptriplet.datasets
import deeptriplet.metrics

# Tensorboard include
from tensorboardX import SummaryWriter

gpu_id = 0

nEpochs = 20  # Number of epochs for training
resume_epoch = 0  # Default is 0, change if want to resume

p = collections.OrderedDict()  # Parameters to include in report
useTest = True  # See evolution of the test set when training
nTestInterval = 1  # Run on test set every nTestInterval epochs
snapshot = 10  # Store a model every snapshot epochs

p['lr'] = 1e-3  # Learning rate
p['wd'] = 5e-4  # Weight decay
p['momentum'] = 0.9  # Momentum
p['poly_power'] = 0.9

save_dir_root = "/srv/glusterfs/yardima/runs/deeplabv2/asppl/"
modelName = 'class-vgg-asppl-pascal'
run_id = 1 
exp_name = 'pascal-deeplabv2-asppl-aug05'

print('Using GPU: {} '.format(gpu_id))
# Setting parameters


save_dir = os.path.join(save_dir_root, 'run_' + str(run_id))


########################## model

net = deeptriplet.models.DeepLab_VGG(version='aspp-l')
net.init_vgg_imagenet()




###########################  optimzers, datasets

init_lr = p['lr']

optimizer = optim.SGD([
                {'params': net.get_parameter_group(bias=False, final=False), 'lr': init_lr},
                {'params': net.get_parameter_group(bias=True, final=False), 'lr': init_lr*2, 'weight_decay':0},
                {'params': net.get_parameter_group(bias=False, final=True), 'lr': init_lr*10},
                {'params': net.get_parameter_group(bias=True, final=True), 'lr': init_lr*20, 'weight_decay':0}
            ], lr=init_lr, momentum=p['momentum'], weight_decay=p['wd'])

loss_fn = nn.CrossEntropyLoss(ignore_index=255)

valset = deeptriplet.datasets.PascalDataset(pascal_root="/scratch/yardima/datasets/voc12/VOCdevkit/VOC2012",
                                            split_file="/home/yardima/Python/experiments/pascal_split/val.txt",
                                            normalize_imagenet=True,
                                            augment=False,
                                            pad_zeros=False,
                                            downsample_label=1)

valloader = data.DataLoader(valset,
                                batch_size=1,
                                num_workers=2,
                                shuffle=False)

trainset = deeptriplet.datasets.PascalDataset(pascal_root="/scratch/yardima/datasets/voc12/VOCdevkit/VOC2012",
                        split_file="/home/yardima/Python/experiments/pascal_split/train.txt",
                        normalize_imagenet=True,
                        augment=True,
                        pad_zeros=True,
                        downsample_label=8)

trainloader = data.DataLoader(trainset,
                                batch_size=10,
                                num_workers=4,
                                shuffle=True)


############################ custom functions

def update_lr_poly(optimizer, init_lr, step, max_step, power):
    lr = init_lr * ((1 - step / float(max_step)) ** (power))
    optimizer.param_groups[0]['lr'] = lr
    optimizer.param_groups[1]['lr'] = 2 * lr
    optimizer.param_groups[2]['lr'] = 10 * lr
    optimizer.param_groups[3]['lr'] = 20 * lr

    return optimizer





################## main script


def generate_param_report(logfile, param):
    log_file = open(logfile, 'w')
    for key, val in param.items():
        log_file.write(key + ':' + str(val) + '\n')
    log_file.close()


if resume_epoch == 0:
    print("Training from init...")
else:
    print("Initializing weights from: {}...".format(
        os.path.join(save_dir, 'models', modelName + '_epoch-' + str(resume_epoch - 1) + '.pth')))
    net.load_state_dict(
        torch.load(os.path.join(save_dir, 'models', modelName + '_epoch-' + str(resume_epoch - 1) + '.pth'),
                   map_location=lambda storage, loc: storage))  # Load all tensors onto the CPU

if gpu_id >= 0:
    torch.cuda.set_device(device=gpu_id)
    net = net.cuda()



if resume_epoch != nEpochs:
    # Logging into Tensorboard
    log_dir = os.path.join(save_dir, 'models', datetime.now().strftime('%b%d_%H-%M-%S') + '_' + socket.gethostname())
    writer = SummaryWriter(log_dir=log_dir)

    # Use the following optimizer
    p['optimizer'] = str(optimizer)

    generate_param_report(os.path.join(save_dir, exp_name + '.txt'), p)

    num_img_tr = len(trainloader)
    num_img_ts = len(valloader)
    running_loss_tr = 0.0
    global_step = 0
    max_steps = nEpochs * num_img_tr
    print("Training Network")

    # Main Training and Testing Loop
    for epoch in range(resume_epoch, nEpochs):
        start_time = timeit.default_timer()

        net.train()
        for ii, sample_batched in enumerate(trainloader):

            inputs, labels = sample_batched
            inputs = inputs.cuda()
            labels = labels.cuda()

            optimizer = update_lr_poly(optimizer, init_lr, global_step, max_steps, p['poly_power'])

            optimizer.zero_grad()

            outputs = net.forward(inputs)
            loss = loss_fn(outputs, labels)

            loss.backward()

            optimizer.step()

            running_loss_tr += loss.item()


            writer.add_scalar('data/total_loss_iter', loss.item(), global_step)
            writer.add_scalar('data/lr', optimizer.param_groups[0]['lr'], global_step)

            global_step += 1

            del loss, outputs


        running_loss_tr = running_loss_tr / num_img_tr
        writer.add_scalar('data/total_loss_epoch', running_loss_tr, epoch)

        print('[Epoch: %d]' % (epoch,))
        print('Loss: %f' % running_loss_tr)
        running_loss_tr = 0.
        stop_time = timeit.default_timer()
        print("Execution time: " + str(stop_time - start_time) + "\n")

        # Save the model
        if (epoch % snapshot) == snapshot - 1:
            torch.save(net.state_dict(), os.path.join(save_dir, 'models', modelName + '_epoch-' + str(epoch) + '.pth'))
            print("Save model at {}\n".format(
                os.path.join(save_dir, 'models', modelName + '_epoch-' + str(epoch) + '.pth')))

        # One testing epoch
        if useTest and epoch % nTestInterval == (nTestInterval - 1):
            net = net.eval()

            miou, acc = deeptriplet.metrics.compute_miou_acc(net, valloader, 21)

            writer.add_scalar('data/val_miou', miou, epoch)
            writer.add_scalar('data/val_acc', acc, epoch)

            net = net.train()

    writer.close()
