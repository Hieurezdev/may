"""Public DTO contracts, grouped by report feature responsibility."""

from .catalog import Variant, Product, StockInput, ProductUpdate, VariantCreate, ProductCreate
from .accounts import Credentials, AddressInput
from .cart import CartInput, CartLine, Voucher, QuoteInput, Quote
from .orders import OrderInput, OrderLine, OrderResult, ShipmentInput, StatusInput
from .payments import PaymentInput, CallbackInput, RefundInput, RefundCallback
from .returns import ReturnLineInput, ReturnInput, ReviewInput, InspectionInput, ReasonInput, ReturnLineView, ReturnView
from .discovery import ConsentInput, TrainInput, SearchInput, EmbeddingResponse, IndexInput
from .experience import TryOnInput, ChatInput, ChatReply

__all__ = [
    'Variant',
    'Product',
    'StockInput',
    'ProductUpdate',
    'VariantCreate',
    'ProductCreate',
    'Credentials',
    'AddressInput',
    'CartInput',
    'CartLine',
    'Voucher',
    'QuoteInput',
    'Quote',
    'OrderInput',
    'OrderLine',
    'OrderResult',
    'ShipmentInput',
    'StatusInput',
    'PaymentInput',
    'CallbackInput',
    'RefundInput',
    'RefundCallback',
    'ReturnLineInput',
    'ReturnInput',
    'ReviewInput',
    'InspectionInput',
    'ReasonInput',
    'ReturnLineView',
    'ReturnView',
    'ConsentInput',
    'TrainInput',
    'SearchInput',
    'EmbeddingResponse',
    'IndexInput',
    'TryOnInput',
    'ChatInput',
    'ChatReply',
]
