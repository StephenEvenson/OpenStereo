import torch.nn.functional as F
import torch 

from modeling.base_model import BaseModel
from .acvnet import ACV_Net
from .acvnet_small import ACV_NetSmall


class ACVLoss:
    def __init__(self):
        self.info = {}

    """ Loss function defined over sequence of flow predictions """

    def model_loss_train_attn_only(self, disp_ests, disp_gt, mask):
        weights = [1.0]
        all_losses = []
        for disp_est, weight in zip(disp_ests, weights):
            all_losses.append(weight * F.smooth_l1_loss(disp_est[mask], disp_gt[mask], size_average=True))
        return sum(all_losses)

    def model_loss_train_freeze_attn(self, disp_ests, disp_gt, mask):
        weights = [0.5, 0.7, 1.0]
        all_losses = []
        for disp_est, weight in zip(disp_ests, weights):
            all_losses.append(weight * F.smooth_l1_loss(disp_est[mask], disp_gt[mask], size_average=True))
        return sum(all_losses)
        
    def model_loss_train(self, disp_ests, disp_gt, mask):
        weights = [0.5, 0.5, 0.7, 1.0] 
        all_losses = []
        for disp_est, weight in zip(disp_ests, weights):
            all_losses.append(weight * F.smooth_l1_loss(disp_est[mask], disp_gt[mask], size_average=True))
        return sum(all_losses)
        
    def model_loss_test(self, disp_ests, disp_gt, mask):
        weights = [1.0] 
        all_losses = []
        for disp_est, weight in zip(disp_ests, weights):
            all_losses.append(weight * F.l1_loss(disp_est[mask], disp_gt[mask], size_average=True))
        return sum(all_losses)

    def __call__(self, training_output):
        disp_ests = training_output["disp"]["disp_ests"]
        disp_gt = training_output["disp"]["disp_gt"]
        mask = training_output["disp"]["mask"]
        total_loss = self.model_loss_train(disp_ests, disp_gt, mask)

        self.info['scalar/total_loss'] = total_loss.item()

        return total_loss, self.info


class ACVNet(BaseModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def build_network(self):
        model_cfg = self.model_cfg
        maxdisp = model_cfg['base_config']['max_disp']
        attn_weights_only = model_cfg['base_config']['attn_weights_only']
        freeze_attn_weights = model_cfg['base_config']['freeze_attn_weights']
        self.net = ACV_Net(maxdisp, attn_weights_only, freeze_attn_weights)
        # self.net.freeze_bn() # legacy, could be removed
    
    """
    def get_loss_func(self, loss_cfg):
        self.loss_fn = ACVLoss()
    """
    
    def build_loss_fn(self):
        loss_cfg = self.cfg['loss_cfg']
        self.loss_fn = ACVLoss()

    def prepare_inputs(self, inputs, device=None):
        """Reorganize input data for different models

        Args:
            inputs: the input data.
            device: the device to put the data.
        Returns:
            dict: training data including ref_img, tgt_img, disp image,
                  and other meta data.
        """
        processed_inputs = {
            'left': inputs['left'],
            'right': inputs['right'],
        }
        if 'disp' in inputs.keys():
            disp_gt = inputs['disp']
            # compute the mask of valid disp_gt
            mask = (disp_gt < self.max_disp) & (disp_gt > 0)
            processed_inputs.update({
                'disp_gt': disp_gt,
                'mask': mask,
            })
        if not self.training:
            for k in ['pad', 'name']:
                if k in inputs.keys():
                    processed_inputs[k] = inputs[k]
        if device is not None:
            # move data to device
            for k, v in processed_inputs.items():
                processed_inputs[k] = v.to(device) if torch.is_tensor(v) else v
        return processed_inputs

    def forward(self, inputs):
        """Forward the network."""
        left = inputs["left"]
        right = inputs["right"]
        if self.training:
            sequence_output = self.net(left, right, training=True)
            output = {
                "training_disp": {
                    "disp": {
                        "disp_ests": sequence_output,
                        "disp_gt": inputs['disp_gt'],
                        "mask": inputs['mask']
                    },
                },
                "visual_summary": {},
            }
        else:
            pred2 = self.net(left, right, training=False)
            # print(pred2[0].shape)
            output = {
                "inference_disp": {
                    "disp_est": pred2[0]
                },
                "visual_summary": {}
            }
        return output
