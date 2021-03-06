import numpy as np

from smarty.errors import assertion
from smarty.metrics import mean_squared_error, accuracy
from .utils import print_epoch, print_step
from .base import MiniBatchGradientDescent, BaseModel, BaseSolver


LINEAR_SOLVERS = (
    "mbgd",
    "norm_eq"
)
"""
:var str mbgd: Mini-Batch Gradient Descent
:var str norm_eq: Normal Equation
"""


class NormalEqSolver(BaseSolver):
    def __init__(self, *args, **kwargs):
        super(NormalEqSolver, self).__init__(*args, **kwargs)
        self.root.bias_ = None
        self.root.coefs_ = None

    def fit(self, ds, predict=True, *args, **kwargs):
        print_epoch(1, 1)
        print_step(0, 1)

        bias = np.ones((len(ds), 1))
        X = np.c_[bias, ds.get_data_classes()]
        y = ds.get_target_classes()

        x_t = X.T
        all_ = np.linalg.inv(x_t.dot(X)).dot(x_t).dot(y)

        self.root.coefs_ = all_[1:]
        self.root.bias_ = all_[0]

        kw = {}
        self.fit_predict(predict, ds, kw)
        print_step(1, 1, **kw)

    def get_params(self):
        kw = super().get_params()

        return kw.update({
            "root__bias_": self.root.bias_,
            "root__coefs_": self.root.coefs_,
            "root__loss": self.root.loss,
        })

    def predict(self, x_b, *args, **kwargs):
        return x_b.dot(self.root.coefs_) + self.root.bias_


class CoefSolver(MiniBatchGradientDescent):
    def gradient_step(self, X_b, y_b):
        """Performs coefficients optimization."""
        y_pred = self.predict(X_b)
        const = self.root.learning_rate_ / self.root.m_
        error = y_pred - y_b

        self.root.coefs_ -= const * X_b.T.dot(error)
        self.root.bias_ -= const * np.sum(error)
        return y_pred

    def fit(self, ds, *args, **kwargs):
        self.root.m_ = len(ds)
        self.root.coefs_ = np.zeros((len(ds.data_classes_), 1))
        self.root.bias_ = np.zeros((1, 1))
        return super().fit(ds, *args, **kwargs)

    def predict(self, x_b):
        return x_b.dot(self.root.coefs_) + self.root.bias_

    def get_params(self):
        kw = super().get_params()
        return kw.update({
            "root__bias_": self.root.bias_,
            "root__coefs_": self.root.coefs_,
        })
    

class LinearSgdSolver(CoefSolver):
    pass


class LogisticSgdSolver(CoefSolver):
    def predict(self, x_b):
        y_pred = x_b.dot(self.root.coefs_) + self.root.bias_
        return (1.0 / (1.0 + np.exp(-y_pred))).astype("i")


class PerceptronSolver(CoefSolver):
    def predict(self, x_b):
        y_pred = x_b.dot(self.root.coefs_) + self.root.bias_
        idxs = np.where(y_pred > self.root.threshold_)
        y_pred = np.zeros(y_pred.shape, dtype=np.unit8)
        y_pred[idxs] = 1
        return y_pred

    def get_params(self): 
        kw = super().get_params()
        return kw.update({
            "root__threshold_": self.root.threshold_
        })


class LinearRegression(BaseModel):
    """Linear model

    :param loss: evaluation loss, has to accept y and y_pred and return score: for pre-defined see smarty.models.metrics
    :param str solver: solver, one of smarty.models.linear.LINEAR_SOLVERS
    :param float learning_rate: learning rate, used only for solver="sgd"
    :var np.ndarray bias\_: model's bias term
    :var np.ndarray coefs\_: model's coefficients
    :var float learning_rate\_: model's learning rate

    .. note::
        If you are using solver="sgd", you can plot training curve via .plot_training() or see each eopch losses - list at .solver_.costs_
    """

    def __init__(self, loss=mean_squared_error, solver="mbgd", learning_rate=0.0001, *args, **kwargs):
        super(LinearRegression, self).__init__(*args, **kwargs)

        assertion(solver in LINEAR_SOLVERS, "Solver unrecognised, see models.linear.LINEAR_SOLVERS to see defined one.")
        if solver == "mbgd":
            self.solver_ = LinearSgdSolver(self)
        else:
            self.solver_ = NormalEqSolver(self)

        self.loss = loss
        self.learning_rate_ = learning_rate # used only for sgd solver

    def clean_copy(self):
        """
        :returns: new unfited model with same parameters
        """
        return LinearRegression(
            loss=self.loss,
            solver="sgd" if isinstance(self.solver_, LinearSgdSolver) else "norm_eq",
            learning_rate=self.learning_rate_
            )

    def get_params(self):
        params = super().get_params()
        params["root__solver"] = "mbgd" if isinstance(self.solver_, LinearSgdSolver) else "norm_eq"
        return params
    

class LogisticClassifier(BaseModel):
    """Logistic binary classifier

    :param loss: evaluation loss, has to accept y and y_pred and return score: for pre-defined see smarty.models.metrics
    :param float learning_rate: learning rate
    :var np.ndarray bias\_: model's bias term
    :var np.ndarray coefs\_: model's coefficients
    :var float learning_rate\_: model's learning rate

    .. note::
        You can plot training curve via .plot_training() or see each eopch losses - list at .solver_.costs_
    """

    def __init__(self, loss=accuracy, learning_rate=0.0001, *args, **kwargs):
        super(LogisticClassifier, self).__init__(*args, **kwargs)
    
        self.loss = loss
        self.solver_ = LogisticSgdSolver(self)
        self.learning_rate_ = learning_rate

    def fit(self, ds, *args, **kwargs):
        # make sure the target class is correct for binary classification
        target = ds.get_target_classes()
        assertion(target.shape[1] == 1, "Binary classifier can have only one class")
        unique = np.unique(target)
        assertion(list(unique) == [0, 1], "Target class must consist only of 0 and 1")

        return super().fit(ds, *args, **kwargs)

    def clean_copy(self):
        """
        :returns: new unfited model with same parameters
        """
        return LogisticClassifier(
            loss=self.loss,
            learning_rate=self.learning_rate_
            )


class Perceptron(BaseModel):
    """Perceptron binary classifier

    :param loss: evaluation loss, has to accept y and y_pred and return score: for pre-defined see smarty.models.metrics
    :param float learning_rate: learning rate
    :param float threshold: values higher than threshold will be classified as 1, rest as 0
    :var np.ndarray bias\_: model's bias term
    :var np.ndarray coefs\_: model's coefficients
    :var float learning_rate\_: model's learning rate

    .. note::
        You can plot training curve via .plot_training() or see each eopch losses - list at .solver_.costs_
    """

    def __init__(self, loss=accuracy, learning_rate=0.0001, threshold=0., *args, **kwargs):
        super(Perceptron, self).__init__(*args, **kwargs)

        self.loss = loss
        self.solver_ = PerceptronSolver(self)
        self.learning_rate_ = learning_rate
        self.threshold_ = threshold

    def fit(self, ds, *args, **kwargs):
        # make sure the target class is correct for binary classification
        target = ds.get_target_classes()
        assertion(target.shape[1] == 1, "Binary classifier can have only one class")
        unique = np.unique(target)
        assertion(list(unique) == [0, 1], "Target class must consist only of 0 and 1")

        return super().fit(ds, *args, **kwargs)

    def clean_copy(self):
        """
        :returns: new unfited model with same parameters
        """
        return Perceptron(
            loss=self.loss,
            learning_rate=self.learning_rate_,
            threshold=self.threshold_
            )
