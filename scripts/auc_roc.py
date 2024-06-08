import logging
import os
import sys

lib_path = os.path.abspath("").replace("scripts", "src")
sys.path.append(lib_path)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
import glob
import argparse
import torch
import matplotlib.pyplot as plt
from data.dataloader import build_train_test_dataset
from tqdm.auto import tqdm
from models import networks
from configs.base import Config
from sklearn.metrics import roc_curve, auc


def eval(cfg, checkpoint_path, all_state_dict=True):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    network = getattr(networks, cfg.model_type)(cfg)
    network.to(device)

    # Build dataset
    _, test_ds = build_train_test_dataset(cfg)
    weight = torch.load(checkpoint_path, map_location=torch.device(device))
    if all_state_dict:
        weight = weight["state_dict_network"]

    network.load_state_dict(weight)
    network.eval()
    network.to(device)

    y_actu = []
    y_pred = []

    for every_test_list in tqdm(test_ds):
        input_ids, audio, label = every_test_list
        input_ids = input_ids.to(device)
        audio = audio.to(device)
        label = label.to(device)
        with torch.no_grad():
            output = network(input_ids, audio)[0]
            _, preds = torch.max(output, 1)
            y_actu.append(label.detach().cpu().numpy()[0])
            y_pred.append(preds.detach().cpu().numpy()[0])
    return y_actu, y_pred


def main(args):
    logging.info("Finding checkpoints")
    test_set = args.test_set if args.test_set is not None else "test.pkl"
    checkpoints = {
        "EmoLens": "",
        "AudioOnly": "",
        "TextOnly": "",
    }
    dataFrame = {}
    dataset_name = ""
    for name, ckpt in checkpoints.items():
        meta_info = ckpt.split("/")
        time = meta_info[-1]
        settings = meta_info[-2]
        model_name = meta_info[-3]
        logging.info("Evaluating: {}/{}/{}".format(model_name, settings, time))
        cfg_path = os.path.join(ckpt, "cfg.log")
        if args.latest:
            ckpt_path = glob.glob(os.path.join(ckpt, "weights", "*.pt"))
            if len(ckpt_path) != 0:
                ckpt_path = ckpt_path[0]
                all_state_dict = True
            else:
                ckpt_path = glob.glob(os.path.join(ckpt, "weights", "*.pth"))[0]
                all_state_dict = False

        else:
            ckpt_path = os.path.join(ckpt, "weights/best_acc/checkpoint_0_0.pt")
            all_state_dict = True
            if not os.path.exists(ckpt_path):
                ckpt_path = os.path.join(ckpt, "weights/best_acc/checkpoint_0.pth")
                all_state_dict = False

        cfg = Config()
        cfg.load(cfg_path)
        # Change to test set
        cfg.data_valid = test_set
        dataset_name = cfg.data_name
        if args.data_root is not None:
            assert (
                args.data_name is not None
            ), "Change validation dataset requires data_name"
            cfg.data_root = args.data_root
            cfg.data_name = args.data_name

        y_true, y_pred = eval(cfg, ckpt_path, all_state_dict=all_state_dict)

        dataFrame["y_true"] = y_true
        dataFrame[name] = y_pred

    # Plot ROC curve for each model
    plt.figure(figsize=(8, 5.5))

    for model in checkpoints.keys():
        fpr, tpr, _ = roc_curve(dataFrame["y_true"], dataFrame[model])
        roc_auc = auc(fpr, tpr)
        plt.plot(fpr, tpr, label=f"{model} (AUC = {roc_auc:.2f})")

    # Plot random guess line
    plt.plot([0, 1], [0, 1], "r--", label="Random Guess")

    # Set labels and title
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("ROC Curves for Two Models")
    plt.legend()
    plt.savefig(
        "AUC_ROC" + dataset_name + args.test_set + ".png",
        format="png",
        dpi=300,
    )


def arg_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-l",
        "--latest",
        action="store_true",
        help="whether to use latest weight or best weight",
    )

    parser.add_argument(
        "-t",
        "--test_set",
        type=str,
        default=None,
        help="name of testing set. Ex: test.pkl",
    )

    parser.add_argument(
        "--data_root",
        type=str,
        default=None,
        help="If want to change the validation dataset",
    )
    parser.add_argument(
        "--data_name", type=str, default=None, help="for changing validation dataset"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = arg_parser()
    main(args)
