# -*- coding: utf-8 -*-


# OpenFisca -- A versatile microsimulation software
# By: OpenFisca Team <contact@openfisca.fr>
#
# Copyright (C) 2011, 2012, 2013, 2014, 2015 OpenFisca Team
# https://github.com/openfisca
#
# This file is part of OpenFisca.
#
# OpenFisca is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# OpenFisca is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


"""Handle legislative parameters in JSON format."""


import collections
import datetime
import itertools
import logging

from . import conv, periods, taxscales


log = logging.getLogger(__name__)
N_ = lambda message: message
units = [
    u'currency',
    u'day',
    u'hour',
    u'month',
    u'year',
    ]


class CompactNode(object):
    # Note: Attributes come from dated_node_json and are not defined in class.

    def __delitem__(self, key):
        del self.__dict__[key]

    def __getitem__(self, key):
        return self.__dict__[key]

    def __iter__(self):
        return self.__dict__.iterkeys()

    def __repr__(self):
        return '{}({})'.format(self.__class__.__name__, repr(self.__dict__))

    def __setitem__(self, key, value):
        self.__dict__[key] = value

    def combine_tax_scales(self):
        """Combine all the MarginalRateTaxScales in the node into a single MarginalRateTaxScale."""
        combined_tax_scales = None
        for name, child in self.iteritems():
            assert isinstance(child, taxscales.AbstractTaxScale), child
            if combined_tax_scales is None:
                combined_tax_scales = taxscales.MarginalRateTaxScale(name = name)
                combined_tax_scales.add_bracket(0, 0)
            combined_tax_scales.add_tax_scale(child)
        return combined_tax_scales

    def copy(self, deep = False):
        new = self.__class__()
        for name, value in self.iteritems():
            if deep:
                if isinstance(value, CompactNode):
                    new[name] = value.copy(deep = deep)
                elif isinstance(value, taxscales.AbstractTaxScale):
                    new[name] = value.copy()
                else:
                    new[name] = value
            else:
                new[name] = value
        return new

    def get(self, key, default = None):
        return self.__dict__.get(key, default)

    def items(self):
        return self.__dict__.items()

    def iteritems(self):
        return self.__dict__.iteritems()

    def iterkeys(self):
        return self.__dict__.iterkeys()

    def itervalues(self):
        return self.__dict__.itervalues()

    def keys(self):
        return self.__dict__.keys()

    def pop(self, key, default = None):
        return self.__dict__.pop(key, default)

    def scale_tax_scales(self, factor):
        """Scale all the MarginalRateTaxScales in the node."""
        scaled_node = CompactNode()
        for key, child in self.iteritems():
            scaled_node[key] = child.scale_tax_scales(factor)
        return scaled_node

    def update(self, value):
        if isinstance(value, CompactNode):
            value = value.__dict__
        return self.__dict__.update(value)

    def values(self):
        return self.__dict__.values()


class CompactRootNode(CompactNode):
    instant = None


# Functions


def compact_dated_node_json(dated_node_json, code = None, instant = None):
    node_type = dated_node_json['@type']
    if node_type == u'Node':
        if code is None:
            # Root node
            assert instant is None, instant
            compact_node = CompactRootNode()
            compact_node.instant = instant = periods.instant(dated_node_json['instant'])
        else:
            assert instant is not None
            compact_node = CompactNode()
        compact_node_dict = compact_node.__dict__
        for key, value in dated_node_json['children'].iteritems():
            compact_node_dict[key] = compact_dated_node_json(value, code = key, instant = instant)
        return compact_node
    assert instant is not None
    if node_type == u'Parameter':
        return dated_node_json.get('value')
    assert node_type == u'Scale'
    if any('amount' in bracket for bracket in dated_node_json['brackets']):
        # AmountTaxScale
        tax_scale = taxscales.AmountTaxScale(name = code, option = dated_node_json.get('option'))
        for dated_bracket_json in dated_node_json['brackets']:
            amount = dated_bracket_json.get('amount')
            assert not isinstance(amount, list)
            threshold = dated_bracket_json.get('threshold')
            assert not isinstance(threshold, list)
            if amount is not None and threshold is not None:
                tax_scale.add_bracket(threshold, amount)
        return tax_scale

    rates_kind = dated_node_json.get('rates_kind', None)
    if rates_kind == "average":
        # LinearAverageRateTaxScale
        tax_scale = taxscales.LinearAverageRateTaxScale(
            name = code,
            option = dated_node_json.get('option'),
            unit = dated_node_json.get('unit'),
            )
    else:
        # MarginalRateTaxScale
        tax_scale = taxscales.MarginalRateTaxScale(name = code, option = dated_node_json.get('option'))

    for dated_bracket_json in dated_node_json['brackets']:
        base = dated_bracket_json.get('base', 1)
        assert not isinstance(base, list)
        rate = dated_bracket_json.get('rate')
        assert not isinstance(rate, list)
        threshold = dated_bracket_json.get('threshold')
        assert not isinstance(threshold, list)
        if rate is not None and threshold is not None:
            tax_scale.add_bracket(threshold, rate * base)
    return tax_scale


def generate_dated_bracket_json(bracket_json, legislation_start_str, legislation_stop_str, instant_str):
    dated_bracket_json = collections.OrderedDict()
    for key, value in bracket_json.iteritems():
        if key in ('amount', 'base', 'rate', 'threshold'):
            dated_value = generate_dated_json_value(value, legislation_start_str, legislation_stop_str, instant_str)
            if dated_value is not None:
                dated_bracket_json[key] = dated_value
        else:
            dated_bracket_json[key] = value
    return dated_bracket_json


def generate_dated_json_value(values_json, legislation_start_str, legislation_stop_str, instant_str):
    max_stop_str = UnboundLocalError
    max_value = None
    min_start_str = None
    min_value = None
    for value_json in values_json:
        value_start_str = value_json['start']
        value_stop_str = value_json.get('stop')
        if value_start_str <= instant_str and (value_stop_str is None or instant_str <= value_stop_str):
            return value_json['value']
        if max_stop_str is UnboundLocalError or value_stop_str is None or value_stop_str > max_stop_str:
            max_stop_str = value_stop_str
            max_value = value_json['value']
        if min_start_str is None or value_start_str < min_start_str:
            min_start_str = value_start_str
            min_value = value_json['value']
    if instant_str > legislation_stop_str:
        # The requested date is after the end of the legislation. Use the value of the last period, when this
        # period ends the same day or after the legislation.
        if max_stop_str is not UnboundLocalError and (max_stop_str is None or max_stop_str >= legislation_stop_str):
            return max_value
    elif instant_str < legislation_start_str:
        # The requested date is before the beginning of the legislation. Use the value of the first period, when this
        # period begins the same day or before the legislation.
        if min_start_str is not None and min_start_str <= legislation_start_str:
            return min_value
    return None


def generate_dated_legislation_json(legislation_json, instant):
    instant_str = str(periods.instant(instant))
    dated_legislation_json = generate_dated_node_json(
        legislation_json,
        legislation_json['start'],
        legislation_json['stop'],
        instant_str,
        )
    dated_legislation_json['@context'] = u'http://openfisca.fr/contexts/dated-legislation.jsonld'
    dated_legislation_json['instant'] = instant_str
    return dated_legislation_json


def generate_dated_node_json(node_json, legislation_start_str, legislation_stop_str, instant_str):
    dated_node_json = collections.OrderedDict()
    for key, value in node_json.iteritems():
        if key == 'children':
            # Occurs when @type == 'Node'.
            dated_children_json = type(value)(
                (child_code, dated_child_json)
                for child_code, dated_child_json in (
                    (
                        child_code,
                        generate_dated_node_json(child_json, legislation_start_str, legislation_stop_str,
                            instant_str),
                        )
                    for child_code, child_json in value.iteritems()
                    )
                if dated_child_json is not None
                )
            if not dated_children_json:
                return None
            dated_node_json[key] = dated_children_json
        elif key in ('start', 'stop'):
            pass
        elif key == 'brackets':
            # Occurs when @type == 'Scale'.
            dated_brackets_json = [
                dated_bracket_json
                for dated_bracket_json in (
                    generate_dated_bracket_json(bracket_json, legislation_start_str, legislation_stop_str, instant_str)
                    for bracket_json in value
                    )
                if dated_bracket_json is not None
                ]
            if not dated_brackets_json:
                return None
            dated_node_json[key] = dated_brackets_json
        elif key == 'values':
            # Occurs when @type == 'Parameter'.
            dated_value = generate_dated_json_value(value, legislation_start_str, legislation_stop_str, instant_str)
            if dated_value is None:
                return None
            dated_node_json['value'] = dated_value
        else:
            dated_node_json[key] = value
    return dated_node_json


# Level-1 Converters


def validate_dated_legislation_json(dated_legislation_json, state = None):
    if dated_legislation_json is None:
        return None, None
    if state is None:
        state = conv.default_state

    dated_legislation_json, error = conv.pipe(
        conv.test_isinstance(dict),
        conv.struct(
            dict(
                instant = conv.pipe(
                    conv.test_isinstance(basestring),
                    conv.iso8601_input_to_date,
                    conv.date_to_iso8601_str,
                    conv.not_none,
                    ),
                ),
            constructor = collections.OrderedDict,
            default = conv.noop,
            drop_none_values = 'missing',
            keep_value_order = True,
            ),
        )(dated_legislation_json, state = state)
    if error is not None:
        return dated_legislation_json, error

    instant = dated_legislation_json.pop('instant')
    dated_legislation_json, error = validate_dated_node_json(dated_legislation_json, state = state)
    dated_legislation_json['instant'] = instant
    return dated_legislation_json, error


def validate_dated_node_json(node, state = None):
    if node is None:
        return None, None
    state = conv.add_ancestor_to_state(state, node)

    validated_node, error = conv.test_isinstance(dict)(node, state = state)
    if error is not None:
        conv.remove_ancestor_from_state(state, node)
        return validated_node, error

    validated_node, errors = conv.struct(
        {
            '@context': conv.pipe(
                conv.test_isinstance(basestring),
                conv.make_input_to_url(full = True),
                conv.test_equals(u'http://openfisca.fr/contexts/dated-legislation.jsonld'),
                ),
            '@type': conv.pipe(
                conv.test_isinstance(basestring),
                conv.cleanup_line,
                conv.test_in((u'Node', u'Parameter', u'Scale')),
                conv.not_none,
                ),
            'comment': conv.pipe(
                conv.test_isinstance(basestring),
                conv.cleanup_text,
                ),
            'description': conv.pipe(
                conv.test_isinstance(basestring),
                conv.cleanup_line,
                ),
            },
        constructor = collections.OrderedDict,
        default = conv.noop,
        drop_none_values = 'missing',
        keep_value_order = True,
        )(validated_node, state = state)
    if errors is not None:
        conv.remove_ancestor_from_state(state, node)
        return validated_node, errors

    validated_node.pop('@context', None)  # Remove optional @context everywhere. It will be added to root node later.
    node_converters = {
        '@type': conv.noop,
        'comment': conv.noop,
        'description': conv.noop,
        }
    node_type = validated_node['@type']
    if node_type == u'Node':
        node_converters.update(dict(
            children = conv.pipe(
                conv.test_isinstance(dict),
                conv.uniform_mapping(
                    conv.pipe(
                        conv.test_isinstance(basestring),
                        conv.cleanup_line,
                        conv.not_none,
                        ),
                    conv.pipe(
                        validate_dated_node_json,
                        conv.not_none,
                        ),
                    ),
                conv.empty_to_none,
                conv.not_none,
                ),
            ))
    elif node_type == u'Parameter':
        node_converters.update(dict(
            format = conv.pipe(
                conv.test_isinstance(basestring),
                conv.input_to_slug,
                conv.test_in([
                    'boolean',
                    'float',
                    'integer',
                    'rate',
                    ]),
                ),
            unit = conv.pipe(
                conv.test_isinstance(basestring),
                conv.input_to_slug,
                conv.test_in(units),
                ),
            value = conv.pipe(
                conv.item_or_sequence(
                    validate_dated_value_json,
                    ),
                conv.not_none,
                ),
            ))
    else:
        assert node_type == u'Scale'
        node_converters.update(dict(
            option = conv.pipe(
                conv.test_isinstance(basestring),
                conv.input_to_slug,
                conv.test_in((
                    'contrib',
                    'main-d-oeuvre',
                    'noncontrib',
                    )),
                ),
            brackets = conv.pipe(
                conv.test_isinstance(list),
                conv.uniform_sequence(
                    validate_dated_bracket_json,
                    drop_none_items = True,
                    ),
                validate_dated_brackets_json_types,
                conv.empty_to_none,
                conv.not_none,
                ),
            unit = conv.pipe(
                conv.test_isinstance(basestring),
                conv.input_to_slug,
                conv.test_in((
                    'currency',
                    )),
                ),
            ))
    validated_node, errors = conv.struct(
        node_converters,
        constructor = collections.OrderedDict,
        drop_none_values = 'missing',
        keep_value_order = True,
        )(validated_node, state = state)

    conv.remove_ancestor_from_state(state, node)
    return validated_node, errors


def validate_dated_bracket_json(bracket, state = None):
    if bracket is None:
        return None, None
    state = conv.add_ancestor_to_state(state, bracket)
    validated_bracket, errors = conv.pipe(
        conv.test_isinstance(dict),
        conv.struct(
            dict(
                amount = conv.item_or_sequence(
                    validate_dated_value_json,
                    ),
                base = conv.item_or_sequence(
                    conv.pipe(
                        validate_dated_value_json,
                        conv.test_greater_or_equal(0),
                        ),
                    ),
                comment = conv.pipe(
                    conv.test_isinstance(basestring),
                    conv.cleanup_text,
                    ),
                rate = conv.item_or_sequence(
                    conv.pipe(
                        validate_dated_value_json,
                        conv.test_between(0, 1),
                        ),
                    ),
                threshold = conv.item_or_sequence(
                    conv.pipe(
                        validate_dated_value_json,
                        conv.test_greater_or_equal(0),
                        ),
                    ),
                ),
            constructor = collections.OrderedDict,
            drop_none_values = 'missing',
            keep_value_order = True,
            ),
        )(bracket, state = state)
    conv.remove_ancestor_from_state(state, bracket)
    return validated_bracket, errors


def validate_dated_brackets_json_types(brackets, state = None):
    if not brackets:
        return brackets, None

    has_amount = any(
        'amount' in bracket
        for bracket in brackets
        )
    if has_amount:
        if state is None:
            state = conv.default_state
        errors = {}
        for bracket_index, bracket in enumerate(brackets):
            if 'base' in bracket:
                errors.setdefault(bracket_index, {})['base'] = state._(u"A scale can't contain both amounts and bases")
            if 'rate' in bracket:
                errors.setdefault(bracket_index, {})['rate'] = state._(u"A scale can't contain both amounts and rates")
        if errors:
            return brackets, errors
    return brackets, None


def validate_dated_value_json(value, state = None):
    if value is None:
        return None, None
    container = state.ancestors[-1]
    value_converter = dict(
        boolean = conv.condition(
            conv.test_isinstance(int),
            conv.test_in((0, 1)),
            conv.test_isinstance(bool),
            ),
        float = conv.condition(
            conv.test_isinstance(int),
            conv.anything_to_float,
            conv.test_isinstance(float),
            ),
        integer = conv.condition(
            conv.test_isinstance(float),
            conv.pipe(
                conv.test(lambda number: round(number) == number),
                conv.function(int),
                ),
            conv.test_isinstance(int),
            ),
        rate = conv.condition(
            conv.test_isinstance(int),
            conv.anything_to_float,
            conv.test_isinstance(float),
            ),
        )[container.get('format') or 'float']  # Only parameters have a "format".
    return value_converter(value, state = state or conv.default_state)


def validate_legislation_json(legislation, state = None):
    if legislation is None:
        return None, None
    if state is None:
        state = conv.default_state

    legislation, error = conv.pipe(
        conv.test_isinstance(dict),
        conv.struct(
            {
                'start': conv.pipe(
                    conv.test_isinstance(basestring),
                    conv.iso8601_input_to_date,
                    conv.date_to_iso8601_str,
                    conv.not_none,
                    ),
                'stop': conv.pipe(
                    conv.test_isinstance(basestring),
                    conv.iso8601_input_to_date,
                    conv.date_to_iso8601_str,
                    conv.not_none,
                    ),
                },
            constructor = collections.OrderedDict,
            default = conv.noop,
            drop_none_values = 'missing',
            keep_value_order = True,
            ),
        )(legislation, state = state)
    if error is not None:
        return legislation, error

    start = legislation.pop('start')
    stop = legislation.pop('stop')
    legislation, error = validate_node_json(legislation, state = state)
    legislation['start'] = start
    legislation['stop'] = stop
    return legislation, error


def validate_node_json(node, state = None):
    if node is None:
        return None, None
    state = conv.add_ancestor_to_state(state, node)

    validated_node, error = conv.test_isinstance(dict)(node, state = state)
    if error is not None:
        conv.remove_ancestor_from_state(state, node)
        return validated_node, error

    validated_node, errors = conv.struct(
        {
            '@context': conv.pipe(
                conv.test_isinstance(basestring),
                conv.make_input_to_url(full = True),
                conv.test_equals(u'http://openfisca.fr/contexts/legislation.jsonld'),
                ),
            '@type': conv.pipe(
                conv.test_isinstance(basestring),
                conv.cleanup_line,
                conv.test_in((u'Node', u'Parameter', u'Scale')),
                conv.not_none,
                ),
            'comment': conv.pipe(
                conv.test_isinstance(basestring),
                conv.cleanup_text,
                ),
            'description': conv.pipe(
                conv.test_isinstance(basestring),
                conv.cleanup_line,
                ),
            },
        constructor = collections.OrderedDict,
        default = conv.noop,
        drop_none_values = 'missing',
        keep_value_order = True,
        )(validated_node, state = state)
    if errors is not None:
        conv.remove_ancestor_from_state(state, node)
        return validated_node, errors

    validated_node.pop('@context', None)  # Remove optional @context everywhere. It will be added to root node later.
    node_converters = {
        '@type': conv.noop,
        'comment': conv.noop,
        'description': conv.noop,
        }
    node_type = validated_node['@type']
    if node_type == u'Node':
        node_converters.update(dict(
            children = conv.pipe(
                conv.test_isinstance(dict),
                conv.uniform_mapping(
                    conv.pipe(
                        conv.test_isinstance(basestring),
                        conv.cleanup_line,
                        conv.not_none,
                        ),
                    conv.pipe(
                        validate_node_json,
                        conv.not_none,
                        ),
                    ),
                conv.empty_to_none,
                conv.not_none,
                ),
            ))
    elif node_type == u'Parameter':
        node_converters.update(dict(
            format = conv.pipe(
                conv.test_isinstance(basestring),
                conv.input_to_slug,
                conv.test_in([
                    'boolean',
                    'float',
                    'integer',
                    'rate',
                    ]),
                ),
            unit = conv.pipe(
                conv.test_isinstance(basestring),
                conv.input_to_slug,
                conv.test_in(units),
                ),
            values = conv.pipe(
                conv.test_isinstance(list),
                conv.uniform_sequence(
                    validate_value_json,
                    drop_none_items = True,
                    ),
                validate_values_json_dates,
                conv.empty_to_none,
                conv.not_none,
                ),
            ))
    else:
        assert node_type == u'Scale'
        node_converters.update(dict(
            option = conv.pipe(
                conv.test_isinstance(basestring),
                conv.input_to_slug,
                conv.test_in((
                    'contrib',
                    'main-d-oeuvre',
                    'noncontrib',
                    )),
                ),
            brackets = conv.pipe(
                conv.test_isinstance(list),
                conv.uniform_sequence(
                    validate_bracket_json,
                    drop_none_items = True,
                    ),
                validate_brackets_json_types,
                validate_brackets_json_dates,
                conv.empty_to_none,
                conv.not_none,
                ),
            unit = conv.pipe(
                conv.test_isinstance(basestring),
                conv.input_to_slug,
                conv.test_in((
                    'currency',
                    )),
                ),
            ))
    validated_node, errors = conv.struct(
        node_converters,
        constructor = collections.OrderedDict,
        drop_none_values = 'missing',
        keep_value_order = True,
        )(validated_node, state = state)

    conv.remove_ancestor_from_state(state, node)
    return validated_node, errors


def validate_bracket_json(bracket, state = None):
    if bracket is None:
        return None, None
    state = conv.add_ancestor_to_state(state, bracket)
    validated_bracket, errors = conv.pipe(
        conv.test_isinstance(dict),
        conv.struct(
            dict(
                amount = validate_values_holder_json,
                base = validate_values_holder_json,
                comment = conv.pipe(
                    conv.test_isinstance(basestring),
                    conv.cleanup_text,
                    ),
                rate = validate_values_holder_json,
                threshold = conv.pipe(
                    validate_values_holder_json,
                    conv.not_none,
                    ),
                ),
            constructor = collections.OrderedDict,
            drop_none_values = 'missing',
            keep_value_order = True,
            ),
        conv.test(lambda bracket: bool(bracket.get('amount')) ^ bool(bracket.get('rate')),
            error = N_(u"Either amount or rate must be provided")),
        )(bracket, state = state)
    conv.remove_ancestor_from_state(state, bracket)
    return validated_bracket, errors


def validate_brackets_json_dates(brackets, state = None):
    if not brackets:
        return brackets, None
    if state is None:
        state = conv.default_state
    errors = {}

    previous_bracket = brackets[0]
    for bracket_index, bracket in enumerate(itertools.islice(brackets, 1, None), 1):
        for key in ('amount', 'base', 'rate', 'threshold'):
            valid_segments = []
            for value_json in (previous_bracket.get(key) or []):
                from_date = datetime.date(*(int(fragment) for fragment in value_json['start'].split('-')))
                # Note: to_date may be None for first valid segment.
                to_date_str = value_json.get('stop')
                to_date = None if to_date_str is None \
                    else datetime.date(*(int(fragment) for fragment in to_date_str.split('-')))
                if valid_segments and valid_segments[-1][0] == to_date + datetime.timedelta(days = 1):
                    valid_segments[-1] = (from_date, valid_segments[-1][1])
                else:
                    valid_segments.append((from_date, to_date))
            for value_index, value_json in enumerate(bracket.get(key) or []):
                from_date = datetime.date(*(int(fragment) for fragment in value_json['start'].split('-')))
                # Note: to_date may be None for first value_json.
                to_date_str = value_json.get('stop')
                to_date = None if to_date_str is None \
                    else datetime.date(*(int(fragment) for fragment in to_date_str.split('-')))
                for valid_segment in valid_segments:
                    valid_to_date = valid_segment[1]
                    if valid_segment[0] <= from_date and (
                            valid_to_date is None or to_date is not None and to_date <= valid_to_date):
                        break
                else:
                    errors.setdefault(bracket_index, {}).setdefault(key, {}).setdefault(value_index,
                        {})['start'] = state._(u"Dates don't belong to valid dates of previous bracket")
        previous_bracket = bracket
    if errors:
        return brackets, errors

    for bracket_index, bracket in enumerate(itertools.islice(brackets, 1, None), 1):
        amount_segments = []
        for value_json in (bracket.get('amount') or []):
            from_date = datetime.date(*(int(fragment) for fragment in value_json['start'].split('-')))
            # Note: to_date may be None for first amount segment.
            to_date_str = value_json.get('stop')
            to_date = None if to_date_str is None \
                else datetime.date(*(int(fragment) for fragment in to_date_str.split('-')))
            if amount_segments and amount_segments[-1][0] == to_date + datetime.timedelta(days = 1):
                amount_segments[-1] = (from_date, amount_segments[-1][1])
            else:
                amount_segments.append((from_date, to_date))

        rate_segments = []
        for value_json in (bracket.get('rate') or []):
            from_date = datetime.date(*(int(fragment) for fragment in value_json['start'].split('-')))
            # Note: to_date may be None for first rate segment.
            to_date_str = value_json.get('stop')
            to_date = None if to_date_str is None \
                else datetime.date(*(int(fragment) for fragment in to_date_str.split('-')))
            if rate_segments and rate_segments[-1][0] == to_date + datetime.timedelta(days = 1):
                rate_segments[-1] = (from_date, rate_segments[-1][1])
            else:
                rate_segments.append((from_date, to_date))

        threshold_segments = []
        for value_json in (bracket.get('threshold') or []):
            from_date = datetime.date(*(int(fragment) for fragment in value_json['start'].split('-')))
            # Note: to_date may be None for first threshold segment.
            to_date_str = value_json.get('stop')
            to_date = None if to_date_str is None \
                else datetime.date(*(int(fragment) for fragment in to_date_str.split('-')))
            if threshold_segments and threshold_segments[-1][0] == to_date + datetime.timedelta(days = 1):
                threshold_segments[-1] = (from_date, threshold_segments[-1][1])
            else:
                threshold_segments.append((from_date, to_date))

        for value_index, value_json in enumerate(bracket.get('base') or []):
            from_date = datetime.date(*(int(fragment) for fragment in value_json['start'].split('-')))
            # Note: to_date may be None for first value_json.
            to_date_str = value_json.get('stop')
            to_date = None if to_date_str is None \
                else datetime.date(*(int(fragment) for fragment in to_date_str.split('-')))
            for rate_segment in rate_segments:
                rate_to_date = rate_segment[1]
                if rate_segment[0] <= from_date and (
                        rate_to_date is None or to_date is not None and to_date <= rate_to_date):
                    break
            else:
                errors.setdefault(bracket_index, {}).setdefault('base', {}).setdefault(value_index,
                    {})['start'] = state._(u"Dates don't belong to rate dates")

        for value_index, value_json in enumerate(bracket.get('amount') or []):
            from_date = datetime.date(*(int(fragment) for fragment in value_json['start'].split('-')))
            # Note: to_date may be None for first value_json.
            to_date_str = value_json.get('stop')
            to_date = None if to_date_str is None \
                else datetime.date(*(int(fragment) for fragment in to_date_str.split('-')))
            for threshold_segment in threshold_segments:
                threshold_to_date = threshold_segment[1]
                if threshold_segment[0] <= from_date and (
                        threshold_to_date is None or to_date is not None and to_date <= threshold_to_date):
                    break
            else:
                errors.setdefault(bracket_index, {}).setdefault('amount', {}).setdefault(value_index,
                    {})['start'] = state._(u"Dates don't belong to threshold dates")

        for value_index, value_json in enumerate(bracket.get('rate') or []):
            from_date = datetime.date(*(int(fragment) for fragment in value_json['start'].split('-')))
            # Note: to_date may be None for first value_json.
            to_date_str = value_json.get('stop')
            to_date = None if to_date_str is None \
                else datetime.date(*(int(fragment) for fragment in to_date_str.split('-')))
            for threshold_segment in threshold_segments:
                threshold_to_date = threshold_segment[1]
                if threshold_segment[0] <= from_date and (
                        threshold_to_date is None or to_date is not None and to_date <= threshold_to_date):
                    break
            else:
                errors.setdefault(bracket_index, {}).setdefault('rate', {}).setdefault(value_index,
                    {})['start'] = state._(u"Dates don't belong to threshold dates")

        for value_index, value_json in enumerate(bracket.get('threshold') or []):
            from_date = datetime.date(*(int(fragment) for fragment in value_json['start'].split('-')))
            # Note: to_date may be None for first value_json.
            to_date_str = value_json.get('stop')
            to_date = None if to_date_str is None \
                else datetime.date(*(int(fragment) for fragment in to_date_str.split('-')))
            for amount_segment in amount_segments:
                amount_to_date = amount_segment[1]
                if amount_segment[0] <= from_date and (
                        amount_to_date is None or to_date is not None and to_date <= amount_to_date):
                    break
            else:
                for rate_segment in rate_segments:
                    rate_to_date = rate_segment[1]
                    if rate_segment[0] <= from_date and (
                            rate_to_date is None or to_date is not None and to_date <= rate_to_date):
                        break
                else:
                    errors.setdefault(bracket_index, {}).setdefault('threshold', {}).setdefault(value_index,
                        {})['start'] = state._(u"Dates don't belong to amount or rate dates")

    return brackets, errors or None


def validate_brackets_json_types(brackets, state = None):
    if not brackets:
        return brackets, None

    has_amount = any(
        'amount' in bracket
        for bracket in brackets
        )
    if has_amount:
        if state is None:
            state = conv.default_state
        errors = {}
        for bracket_index, bracket in enumerate(brackets):
            if 'base' in bracket:
                errors.setdefault(bracket_index, {})['base'] = state._(u"A scale can't contain both amounts and bases")
            if 'rate' in bracket:
                errors.setdefault(bracket_index, {})['rate'] = state._(u"A scale can't contain both amounts and rates")
        if errors:
            return brackets, errors
    return brackets, None


def validate_value_json(value, state = None):
    if value is None:
        return None, None
    container = state.ancestors[-1]
    value_converter = dict(
        boolean = conv.condition(
            conv.test_isinstance(int),
            conv.test_in((0, 1)),
            conv.test_isinstance(bool),
            ),
        float = conv.condition(
            conv.test_isinstance(int),
            conv.anything_to_float,
            conv.test_isinstance(float),
            ),
        integer = conv.condition(
            conv.test_isinstance(float),
            conv.pipe(
                conv.test(lambda number: round(number) == number),
                conv.function(int),
                ),
            conv.test_isinstance(int),
            ),
        rate = conv.condition(
            conv.test_isinstance(int),
            conv.anything_to_float,
            conv.test_isinstance(float),
            ),
        )[container.get('format') or 'float']  # Only parameters have a "format".
    state = conv.add_ancestor_to_state(state, value)
    validated_value, errors = conv.pipe(
        conv.test_isinstance(dict),
        conv.struct(
            {
                u'comment': conv.pipe(
                    conv.test_isinstance(basestring),
                    conv.cleanup_text,
                    ),
                u'start': conv.pipe(
                    conv.test_isinstance(basestring),
                    conv.iso8601_input_to_date,
                    conv.date_to_iso8601_str,
                    conv.not_none,
                    ),
                u'stop': conv.pipe(
                    conv.test_isinstance(basestring),
                    conv.iso8601_input_to_date,
                    conv.date_to_iso8601_str,
                    ),
                u'value': conv.pipe(
                    value_converter,
                    conv.not_none,
                    ),
                },
            constructor = collections.OrderedDict,
            drop_none_values = 'missing',
            keep_value_order = True,
            ),
        )(value, state = state)
    conv.remove_ancestor_from_state(state, value)
    return validated_value, errors


def validate_values_json_dates(values_json, state = None):
    if not values_json:
        return values_json, None
    if state is None:
        state = conv.default_state

    errors = {}
    for index, value_json in enumerate(values_json):
        stop_date_str = value_json.get('stop')
        if stop_date_str is not None and value_json['start'] > stop_date_str:
            errors[index] = dict(to = state._(u"Last date must be greater than first date"))

    sorted_values_json = sorted(values_json, key = lambda value_json: value_json['start'], reverse = True)
    next_value_json = sorted_values_json[0]
    for index, value_json in enumerate(itertools.islice(sorted_values_json, 1, None)):
        next_date_str = (datetime.date(*(int(fragment) for fragment in value_json['stop'].split('-')))
            + datetime.timedelta(days = 1)).isoformat()
        if next_date_str > next_value_json['start']:
            errors.setdefault(index, {})['start'] = state._(u"Dates of values overlap")
        next_value_json = value_json

    return sorted_values_json, errors or None


validate_values_holder_json = conv.pipe(
    conv.test_isinstance(list),
    conv.uniform_sequence(
        validate_value_json,
        drop_none_items = True,
        ),
    validate_values_json_dates,
    conv.empty_to_none,
    )


# Level-2 Converters


validate_any_legislation_json = conv.pipe(
    conv.test_isinstance(dict),
    conv.condition(
        conv.test(lambda legislation_json: 'datesim' in legislation_json),
        validate_dated_legislation_json,
        validate_legislation_json,
        ),
    )
